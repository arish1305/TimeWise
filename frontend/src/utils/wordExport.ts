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
    section?: {
        name?: string | null;
        academic_year?: {
            name?: string | null;
            department?: {
                name?: string | null;
                code?: string | null;
            } | null;
        } | null;
    } | null;
    entries: TimetableEntry[];
    time_slots?: TimeSlot[];
};

const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'];

const escapeHtml = (value: string | number | null | undefined) =>
    String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');

const formatTime = (time?: string | null) => {
    if (!time) return '';
    const [hour, minute] = time.split(':');
    return `${Number(hour)}.${minute}`;
};

const verticalText = (value: string) =>
    value
        .toUpperCase()
        .split('')
        .map(escapeHtml)
        .join('<br>');

const safeFileName = (value: string) =>
    value
        .trim()
        .replace(/[\\/:*?"<>|]+/g, '-')
        .replace(/\s+/g, '_')
        .slice(0, 120) || 'timetable';

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

const downloadHtmlAsWord = (html: string, filename: string) => {
    const blob = new Blob(['\ufeff', html], { type: 'application/msword;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
};

const buildCourseRows = (timetable: SectionTimetable) => {
    const subjectMap = new Map<number, {
        code: string;
        name: string;
        faculty: Set<string>;
    }>();

    timetable.entries.forEach((entry) => {
        if (!subjectMap.has(entry.subject_id)) {
            subjectMap.set(entry.subject_id, {
                code: entry.subject?.code || 'N/A',
                name: entry.subject?.name || 'Unnamed Course',
                faculty: new Set<string>(),
            });
        }

        if (entry.faculty?.name) {
            subjectMap.get(entry.subject_id)?.faculty.add(entry.faculty.name);
        }
    });

    return Array.from(subjectMap.values())
        .sort((a, b) => a.code.localeCompare(b.code))
        .map((subject, index) => {
            const staff = Array.from(subject.faculty);
            const staffText = staff.length ? staff.join(' / ') : 'Unassigned';
            return `
                <tr>
                    <td class="center">${index + 1}</td>
                    <td class="center">${escapeHtml(subject.code)}</td>
                    <td>${escapeHtml(subject.name)}</td>
                    <td>${escapeHtml(staffText)}</td>
                    <td>${escapeHtml(staff[0] || 'Unassigned')}</td>
                </tr>
            `;
        })
        .join('');
};

const buildTimetableRows = (timetable: SectionTimetable, timeSlots: TimeSlot[]) => {
    const timeRanges = uniqueTimeRangesFromSlots(timeSlots);
    const entriesBySlot = new Map<number, TimetableEntry[]>();

    timetable.entries.forEach((entry) => {
        const entries = entriesBySlot.get(entry.timeslot_id) || [];
        entries.push(entry);
        entriesBySlot.set(entry.timeslot_id, entries);
    });

    return days.map((day, dayIndex) => {
        const cells = timeRanges.map((range) => {
            if (range.is_break) {
                if (dayIndex > 0) return '';
                return `<td class="break-cell" rowspan="${days.length}">${verticalText(range.label || 'Break')}</td>`;
            }

            const slot = timeSlots.find((item) => item.day === day && item.start_time === range.start);
            const entries = slot ? entriesBySlot.get(slot.id) || [] : [];
            const label = entries
                .map((entry) => escapeHtml(entry.subject?.code || 'N/A'))
                .join('<br>');
            return `<td class="center">${label}</td>`;
        }).join('');

        return `
            <tr>
                <td class="day-cell">${escapeHtml(day.toUpperCase())}</td>
                ${cells}
            </tr>
        `;
    }).join('');
};

const buildTimetableDocument = (timetable: SectionTimetable, timeSlots: TimeSlot[], isLast: boolean) => {
    const resolvedTimeSlots = timetable.time_slots?.length ? timetable.time_slots : timeSlots;
    const timeRanges = uniqueTimeRangesFromSlots(resolvedTimeSlots);
    const year = timetable.section?.academic_year?.name || '';
    const section = timetable.section?.name || '';
    const semester = timetable.semester ? String(timetable.semester) : '';
    const department = timetable.section?.academic_year?.department?.name || '';

    return `
        <section class="${isLast ? '' : 'page-break'}">
            <div class="department-title">${escapeHtml(department)}</div>
            <table class="meta-table">
                <tr>
                    <td><b>YEAR:</b> ${escapeHtml(year)}</td>
                    <td><b>SEMESTER:</b> ${escapeHtml(semester)}</td>
                    <td><b>BATCH:</b></td>
                    <td><b>SECTION:</b> ${escapeHtml(section)}</td>
                    <td><b>Hall:</b></td>
                </tr>
            </table>

            <table class="timetable-table">
                <thead>
                    <tr>
                        <th>DAY/TIMING</th>
                        ${timeRanges.map((range) => `
                            <th>
                                ${escapeHtml(formatTime(range.start))}<br>
                                -<br>
                                ${escapeHtml(formatTime(range.end))}
                            </th>
                        `).join('')}
                    </tr>
                </thead>
                <tbody>
                    ${buildTimetableRows(timetable, resolvedTimeSlots)}
                </tbody>
            </table>

            <table class="course-table">
                <thead>
                    <tr>
                        <th>S.No.</th>
                        <th>Course<br>Code</th>
                        <th>Name of the Course</th>
                        <th>Course Handling Staff</th>
                        <th>Course Coordinator</th>
                    </tr>
                </thead>
                <tbody>
                    ${buildCourseRows(timetable)}
                </tbody>
            </table>
        </section>
    `;
};

export const downloadAllTimetablesWord = (timetables: SectionTimetable[], timeSlots: TimeSlot[]) => {
    if (!timetables.length) {
        throw new Error('No generated timetables found.');
    }

    const body = timetables
        .map((timetable, index) => buildTimetableDocument(timetable, timeSlots, index === timetables.length - 1))
        .join('');

    const html = `
        <!doctype html>
        <html>
            <head>
                <meta charset="utf-8">
                <style>
                    @page { size: A4 portrait; margin: 0.35in; }
                    body { font-family: "Times New Roman", serif; font-size: 10pt; color: #000; }
                    table { border-collapse: collapse; width: 100%; table-layout: fixed; }
                    th, td { border: 1px solid #000; padding: 3px 4px; vertical-align: middle; }
                    th { font-weight: bold; text-align: center; }
                    .department-title { font-size: 11pt; font-weight: bold; text-align: center; text-transform: uppercase; margin-bottom: 4px; }
                    .meta-table td { border: 0; font-size: 11pt; font-weight: bold; text-align: center; padding: 0 4px 4px; }
                    .timetable-table { margin-bottom: 12px; }
                    .timetable-table th { font-size: 8pt; line-height: 1.05; }
                    .timetable-table td { height: 21px; font-size: 8pt; }
                    .day-cell { width: 16%; text-align: center; font-weight: bold; }
                    .break-cell { width: 8%; text-align: center; font-weight: bold; line-height: 1.1; }
                    .center { text-align: center; }
                    .course-table th { font-size: 8pt; }
                    .course-table td { font-size: 8pt; line-height: 1.1; }
                    .course-table th:nth-child(1), .course-table td:nth-child(1) { width: 7%; }
                    .course-table th:nth-child(2), .course-table td:nth-child(2) { width: 14%; }
                    .course-table th:nth-child(3), .course-table td:nth-child(3) { width: 31%; }
                    .course-table th:nth-child(4), .course-table td:nth-child(4) { width: 24%; }
                    .course-table th:nth-child(5), .course-table td:nth-child(5) { width: 24%; }
                    .page-break { page-break-after: always; }
                </style>
            </head>
            <body>${body}</body>
        </html>
    `;

    downloadHtmlAsWord(html, `TimeWise_Timetables_${safeFileName(new Date().toISOString().slice(0, 10))}.doc`);
};
