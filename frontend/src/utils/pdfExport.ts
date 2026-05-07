import type { jsPDF } from 'jspdf';

type TimeSlot = {
    id: number;
    day: string;
    start_time: string;
    end_time: string;
    is_break?: boolean;
    label?: string | null;
};

type TimetableEntry = {
    subject_id: number;
    faculty_id?: number | null;
    timeslot_id: number;
    subject?: {
        code?: string | null;
        name?: string | null;
        is_elective?: boolean;
        elective_group_id?: string | null;
    } | null;
    faculty?: {
        id: number;
        name: string;
    } | null;
};

type SectionTimetable = {
    id: number;
    semester: number;
    status?: string;
    version?: number;
    created_at?: string | null;
    section?: {
        name?: string | null;
        academic_year?: {
            name?: string | null;
        } | null;
    } | null;
    entries: TimetableEntry[];
};

type FacultyTimetableEntry = {
    timetable_id: number;
    timetable_status: string;
    semester: number;
    section_id: number;
    section_name: string;
    academic_year_name?: string | null;
    department_code?: string | null;
    subject_id: number;
    subject_code?: string | null;
    subject_name?: string | null;
    timeslot_id: number;
    day?: string | null;
    start_time?: string | null;
    end_time?: string | null;
};

type FacultyTimetable = {
    faculty_id: number;
    faculty_name: string;
    faculty_id_code?: string | null;
    entries: FacultyTimetableEntry[];
};

const sectionDays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'];
const facultyDays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

const palette = {
    ink: '#0f172a',
    muted: '#64748b',
    line: '#dbeafe',
    softLine: '#e2e8f0',
    page: '#f8fafc',
    primary: '#2563eb',
    primaryDark: '#1e40af',
    primarySoft: '#eff6ff',
    filled: '#ffffff',
    empty: '#f1f5f9',
    breakBg: '#fff7ed',
    breakLine: '#fdba74',
};

const formatTime = (time?: string | null) => {
    if (!time) return '-';
    const [hour, minute] = time.split(':');
    return `${Number(hour)}:${minute}`;
};

const safeFileName = (value: string) =>
    value
        .trim()
        .replace(/[\\/:*?"<>|]+/g, '-')
        .replace(/\s+/g, '_')
        .slice(0, 120) || 'timetable';

const downloadBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
};

const addBrandHeader = (doc: jsPDF, title: string, subtitle: string) => {
    const pageWidth = doc.internal.pageSize.getWidth();
    doc.setFillColor(palette.page);
    doc.rect(0, 0, pageWidth, 24, 'F');
    doc.setFillColor(palette.primary);
    doc.roundedRect(12, 7, 10, 10, 2, 2, 'F');
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(palette.ink);
    doc.setFontSize(15);
    doc.text(title, 27, 11.5);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(palette.muted);
    doc.setFontSize(8);
    doc.text(subtitle, 27, 17);
};

const addInfoPills = (doc: jsPDF, items: Array<{ label: string; value: string }>, y: number) => {
    let x = 12;
    items.forEach((item) => {
        const value = item.value || '-';
        doc.setFontSize(6.5);
        doc.setFont('helvetica', 'bold');
        doc.setTextColor(palette.muted);
        doc.text(item.label.toUpperCase(), x, y);

        const width = Math.max(24, doc.getTextWidth(value) + 8);
        doc.setFillColor(palette.primarySoft);
        doc.setDrawColor(palette.line);
        doc.roundedRect(x, y + 2, width, 7.5, 2, 2, 'FD');
        doc.setTextColor(palette.ink);
        doc.setFontSize(7.5);
        doc.text(value, x + 4, y + 7.2);
        x += width + 9;
    });
};

const uniqueTimeRangesFromSlots = (timeSlots: TimeSlot[]) => {
    const seen = new Set<string>();
    return timeSlots
        .slice()
        .sort((a, b) => `${a.start_time}-${a.end_time}`.localeCompare(`${b.start_time}-${b.end_time}`))
        .filter((slot) => {
            const key = `${slot.start_time}-${slot.end_time}`;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        })
        .map((slot) => ({
            start: slot.start_time,
            end: slot.end_time,
            is_break: slot.is_break,
            label: slot.label,
        }));
};

const drawCellText = (doc: jsPDF, text: string, x: number, y: number, width: number, lineHeight = 3.5) => {
    const lines = doc.splitTextToSize(text, Math.max(8, width - 4)).slice(0, 4);
    lines.forEach((line: string, index: number) => {
        doc.text(line, x + width / 2, y + index * lineHeight, { align: 'center' });
    });
};

const drawSectionGrid = (doc: jsPDF, timetable: SectionTimetable, timeSlots: TimeSlot[], startY: number) => {
    const pageWidth = doc.internal.pageSize.getWidth();
    const margin = 10;
    const dayWidth = 22;
    const times = uniqueTimeRangesFromSlots(timeSlots);
    const gridWidth = pageWidth - margin * 2;
    const cellWidth = (gridWidth - dayWidth) / Math.max(times.length, 1);
    const headerHeight = 13;
    const rowHeight = 23;

    const entriesBySlot = new Map<number, TimetableEntry[]>();
    timetable.entries.forEach((entry) => {
        const list = entriesBySlot.get(entry.timeslot_id) || [];
        list.push(entry);
        entriesBySlot.set(entry.timeslot_id, list);
    });

    doc.setFont('helvetica', 'bold');
    doc.setFontSize(7);
    doc.setTextColor(palette.muted);
    doc.setDrawColor(palette.line);
    doc.setFillColor('#ffffff');

    doc.roundedRect(margin, startY, dayWidth, headerHeight, 2, 2, 'FD');
    doc.text('DAY / TIME', margin + dayWidth / 2, startY + 8, { align: 'center' });

    times.forEach((time, index) => {
        const x = margin + dayWidth + index * cellWidth;
        doc.roundedRect(x + 1, startY, cellWidth - 2, headerHeight, 2, 2, 'FD');
        doc.text(`${formatTime(time.start)} - ${formatTime(time.end)}`, x + cellWidth / 2, startY + 8, { align: 'center' });
    });

    sectionDays.forEach((day, dayIndex) => {
        const y = startY + headerHeight + 2 + dayIndex * rowHeight;
        doc.setFillColor('#ffffff');
        doc.setDrawColor(palette.softLine);
        doc.roundedRect(margin, y, dayWidth, rowHeight - 2, 2, 2, 'FD');
        doc.setTextColor(palette.primaryDark);
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(8);
        doc.text(day.substring(0, 3).toUpperCase(), margin + dayWidth / 2, y + rowHeight / 2, { align: 'center' });

        times.forEach((time, timeIndex) => {
            const x = margin + dayWidth + timeIndex * cellWidth;
            const slot = timeSlots.find((item) => item.day === day && item.start_time === time.start);

            if (time.is_break) {
                doc.setFillColor(palette.breakBg);
                doc.setDrawColor(palette.breakLine);
                doc.roundedRect(x + 1, y, cellWidth - 2, rowHeight - 2, 2, 2, 'FD');
                doc.setTextColor('#c2410c');
                doc.setFontSize(7);
                doc.text((time.label || 'BREAK').toUpperCase(), x + cellWidth / 2, y + rowHeight / 2, { align: 'center' });
                return;
            }

            const entries = slot ? entriesBySlot.get(slot.id) || [] : [];
            doc.setFillColor(entries.length ? palette.filled : palette.empty);
            doc.setDrawColor(entries.length ? palette.softLine : '#cbd5e1');
            doc.roundedRect(x + 1, y, cellWidth - 2, rowHeight - 2, 2, 2, 'FD');

            if (entries.length) {
                doc.setFillColor(palette.primary);
                doc.rect(x + 1, y, 1.5, rowHeight - 2, 'F');
                doc.setTextColor(palette.primaryDark);
                doc.setFont('helvetica', 'bold');
                doc.setFontSize(entries.length > 2 ? 5.5 : 7.5);
                const label = entries
                    .map((entry) => {
                        const code = entry.subject?.code || 'N/A';
                        const group = entry.subject?.is_elective && entry.subject?.elective_group_id
                            ? ` (${entry.subject.elective_group_id})`
                            : '';
                        return `${code}${group}`;
                    })
                    .join('\n');
                drawCellText(doc, label, x + 1, y + 8, cellWidth - 2, entries.length > 2 ? 3 : 4);
            }
        });
    });

    return startY + headerHeight + 2 + sectionDays.length * rowHeight + 8;
};

const drawFacultyLegend = (doc: jsPDF, timetable: SectionTimetable, startY: number) => {
    const facultyMap = new Map<number, { name: string; subjects: Set<string> }>();
    timetable.entries.forEach((entry) => {
        if (!entry.faculty) return;
        if (!facultyMap.has(entry.faculty.id)) {
            facultyMap.set(entry.faculty.id, { name: entry.faculty.name, subjects: new Set() });
        }
        facultyMap.get(entry.faculty.id)?.subjects.add(`${entry.subject?.code || 'N/A'} (${entry.subject?.name || 'Subject'})`);
    });

    if (!facultyMap.size) return;

    doc.setFont('helvetica', 'bold');
    doc.setFontSize(9);
    doc.setTextColor(palette.ink);
    doc.text('Faculty & Elective Mapping', 12, startY);

    let y = startY + 5;
    Array.from(facultyMap.values()).slice(0, 12).forEach((faculty) => {
        doc.setFillColor(palette.page);
        doc.setDrawColor(palette.softLine);
        doc.roundedRect(12, y, 130, 10, 2, 2, 'FD');
        doc.setTextColor(palette.primaryDark);
        doc.setFontSize(7);
        doc.setFont('helvetica', 'bold');
        doc.text(faculty.name, 15, y + 4);
        doc.setFont('helvetica', 'normal');
        doc.setTextColor(palette.muted);
        doc.text(Array.from(faculty.subjects).slice(0, 3).join(' | '), 15, y + 8);
        y += 12;
    });
};

const renderSectionTimetablePage = (doc: jsPDF, timetable: SectionTimetable, timeSlots: TimeSlot[]) => {
    const year = timetable.section?.academic_year?.name || 'Unknown Year';
    const section = timetable.section?.name || 'Unknown';
    addBrandHeader(doc, 'TimeWise Section Timetable', `${year} - Section ${section}`);
    addInfoPills(doc, [
        { label: 'Year', value: year },
        { label: 'Semester', value: String(timetable.semester || '-') },
        { label: 'Section', value: section },
        { label: 'Status', value: timetable.status || '-' },
        { label: 'Version', value: String(timetable.version || 1) },
    ], 30);
    const nextY = drawSectionGrid(doc, timetable, timeSlots, 45);
    drawFacultyLegend(doc, timetable, nextY);
};

export const downloadAllTimetablesPdf = async (timetables: SectionTimetable[], timeSlots: TimeSlot[]) => {
    if (!timetables.length) {
        throw new Error('No generated timetables found.');
    }

    const { jsPDF } = await import('jspdf');
    const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });
    timetables.forEach((timetable, index) => {
        if (index > 0) doc.addPage('a4', 'landscape');
        renderSectionTimetablePage(doc, timetable, timeSlots);
    });
    doc.save(`TimeWise_All_Timetables_${new Date().toISOString().slice(0, 10)}.pdf`);
};

const uniqueTimeRangesFromFacultyEntries = (entries: FacultyTimetableEntry[]) =>
    Array.from(new Set(entries.map((entry) => `${entry.start_time || ''}-${entry.end_time || ''}`)))
        .filter((range) => range !== '-')
        .sort()
        .map((range) => {
            const [start, end] = range.split('-');
            return { start, end };
        });

const drawFacultyGrid = (doc: jsPDF, timetable: FacultyTimetable, startY: number) => {
    const pageWidth = doc.internal.pageSize.getWidth();
    const margin = 10;
    const dayWidth = 27;
    const times = uniqueTimeRangesFromFacultyEntries(timetable.entries);
    const gridWidth = pageWidth - margin * 2;
    const cellWidth = (gridWidth - dayWidth) / Math.max(times.length, 1);
    const headerHeight = 13;
    const rowHeight = 22;

    const entriesByCell = new Map<string, FacultyTimetableEntry[]>();
    timetable.entries.forEach((entry) => {
        const key = `${entry.day}-${entry.start_time}-${entry.end_time}`;
        const list = entriesByCell.get(key) || [];
        list.push(entry);
        entriesByCell.set(key, list);
    });

    doc.setFont('helvetica', 'bold');
    doc.setFontSize(7);
    doc.setTextColor(palette.muted);
    doc.setDrawColor(palette.line);
    doc.setFillColor('#ffffff');
    doc.roundedRect(margin, startY, dayWidth, headerHeight, 2, 2, 'FD');
    doc.text('DAY / TIME', margin + dayWidth / 2, startY + 8, { align: 'center' });

    times.forEach((time, index) => {
        const x = margin + dayWidth + index * cellWidth;
        doc.roundedRect(x + 1, startY, cellWidth - 2, headerHeight, 2, 2, 'FD');
        doc.text(`${formatTime(time.start)} - ${formatTime(time.end)}`, x + cellWidth / 2, startY + 8, { align: 'center' });
    });

    facultyDays.forEach((day, dayIndex) => {
        const y = startY + headerHeight + 2 + dayIndex * rowHeight;
        doc.setFillColor('#ffffff');
        doc.setDrawColor(palette.softLine);
        doc.roundedRect(margin, y, dayWidth, rowHeight - 2, 2, 2, 'FD');
        doc.setTextColor(palette.primaryDark);
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(7.5);
        doc.text(day, margin + dayWidth / 2, y + rowHeight / 2, { align: 'center' });

        times.forEach((time, timeIndex) => {
            const x = margin + dayWidth + timeIndex * cellWidth;
            const entries = entriesByCell.get(`${day}-${time.start}-${time.end}`) || [];
            doc.setFillColor(entries.length ? palette.filled : palette.empty);
            doc.setDrawColor(entries.length ? palette.softLine : '#cbd5e1');
            doc.roundedRect(x + 1, y, cellWidth - 2, rowHeight - 2, 2, 2, 'FD');

            if (!entries.length) return;
            doc.setFillColor(palette.primary);
            doc.rect(x + 1, y, 1.5, rowHeight - 2, 'F');
            doc.setTextColor(palette.primaryDark);
            doc.setFont('helvetica', 'bold');
            doc.setFontSize(entries.length > 1 ? 5.5 : 6.5);
            const label = entries.map((entry) => {
                const section = `${entry.department_code || ''} ${entry.academic_year_name || ''} Sec ${entry.section_name}`.trim();
                return `${entry.subject_code || entry.subject_name || 'Subject'}\n${section}`;
            }).join('\n');
            drawCellText(doc, label, x + 1, y + 6, cellWidth - 2, 3.3);
        });
    });
};

const renderFacultyTimetablePage = (doc: jsPDF, timetable: FacultyTimetable) => {
    const code = timetable.faculty_id_code ? ` (${timetable.faculty_id_code})` : '';
    addBrandHeader(doc, 'TimeWise Faculty Timetable', `${timetable.faculty_name}${code}`);
    addInfoPills(doc, [
        { label: 'Faculty', value: timetable.faculty_name },
        { label: 'Faculty ID', value: timetable.faculty_id_code || '-' },
        { label: 'Classes', value: String(timetable.entries.length) },
        { label: 'Sections', value: String(new Set(timetable.entries.map((entry) => entry.section_id)).size) },
    ], 30);

    if (!timetable.entries.length) {
        doc.setTextColor(palette.muted);
        doc.setFontSize(11);
        doc.text('No timetable entries are assigned to this faculty yet.', 12, 55);
        return;
    }

    drawFacultyGrid(doc, timetable, 45);
};

export const downloadFacultyTimetablePdf = async (timetable: FacultyTimetable) => {
    const { jsPDF } = await import('jspdf');
    const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });
    renderFacultyTimetablePage(doc, timetable);
    doc.save(`${safeFileName(timetable.faculty_name)}_Timetable.pdf`);
};

export const downloadAllFacultyTimetablesZip = async (facultyTimetables: FacultyTimetable[]) => {
    if (!facultyTimetables.length) {
        throw new Error('No faculty records found.');
    }

    const { jsPDF } = await import('jspdf');
    const { default: JSZip } = await import('jszip');
    const zip = new JSZip();
    facultyTimetables.forEach((timetable) => {
        const doc = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });
        renderFacultyTimetablePage(doc, timetable);
        const code = timetable.faculty_id_code ? `_${timetable.faculty_id_code}` : '';
        zip.file(`${safeFileName(`${timetable.faculty_name}${code}`)}_Timetable.pdf`, doc.output('blob'));
    });

    const blob = await zip.generateAsync({ type: 'blob' });
    downloadBlob(blob, `TimeWise_Faculty_Timetables_${new Date().toISOString().slice(0, 10)}.zip`);
};
