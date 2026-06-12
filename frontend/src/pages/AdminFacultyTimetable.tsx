import { useEffect, useState } from 'react';
import { Calendar, Download, RefreshCw, Search, Users } from 'lucide-react';
import api from '../api/axios';
import { downloadAllFacultyTimetablesZip, downloadFacultyTimetablePdf } from '../utils/pdfExport';
import AppLogo from '../components/AppLogo';
import { formatTime12Hour } from '../utils/timeFormat';

interface FacultyOption {
    id: number;
    name: string;
    faculty_id_code?: string | null;
}

interface FacultyTimetableEntry {
    timetable_id: number;
    timetable_status: string;
    semester: number;
    section_id: number;
    section_name: string;
    academic_year_name?: string | null;
    department_name?: string | null;
    department_code?: string | null;
    subject_id: number;
    subject_code?: string | null;
    subject_name?: string | null;
    timeslot_id: number;
    day?: string | null;
    start_time?: string | null;
    end_time?: string | null;
    is_locked: boolean;
    created_by: string;
}

interface FacultyTimetableResponse {
    faculty_id: number;
    faculty_name: string;
    faculty_id_code?: string | null;
    entries: FacultyTimetableEntry[];
}

const dayOrder = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

const AdminFacultyTimetable = () => {
    const [facultyList, setFacultyList] = useState<FacultyOption[]>([]);
    const [selectedFacultyId, setSelectedFacultyId] = useState('');
    const [facultyIdCode, setFacultyIdCode] = useState('');
    const [facultyName, setFacultyName] = useState('');
    const [data, setData] = useState<FacultyTimetableResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [exportingSelected, setExportingSelected] = useState(false);
    const [exportingAll, setExportingAll] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchFaculty = async () => {
            try {
                const res = await api.get('/admin/faculty');
                setFacultyList(res.data);
            } catch (err) {
                console.error(err);
                setError('Failed to load faculty list.');
            }
        };

        fetchFaculty();
    }, []);

    const handleFacultySelect = (value: string) => {
        setSelectedFacultyId(value);
        const selected = facultyList.find((faculty) => faculty.id === Number(value));
        if (selected) {
            setFacultyName(selected.name);
            setFacultyIdCode(selected.faculty_id_code || '');
        }
    };

    const searchTimetable = async () => {
        setLoading(true);
        setError(null);
        setData(null);

        try {
            const params: Record<string, string | number> = {};
            if (selectedFacultyId) {
                params.faculty_id = Number(selectedFacultyId);
            }
            if (facultyIdCode.trim()) {
                params.faculty_id_code = facultyIdCode.trim();
            }
            if (facultyName.trim()) {
                params.faculty_name = facultyName.trim();
            }

            const res = await api.get('/timetables/faculty', { params });
            setData(res.data);
        } catch (err: any) {
            console.error(err);
            setError(err.response?.data?.detail || 'Failed to load faculty timetable.');
        } finally {
            setLoading(false);
        }
    };

    const downloadSelectedFacultyPdf = async () => {
        if (!data) {
            setError('Search and open a faculty timetable before downloading it.');
            return;
        }

        setExportingSelected(true);
        try {
            await downloadFacultyTimetablePdf(data);
        } catch (err: any) {
            console.error('Failed to export faculty timetable', err);
            setError(err.message || 'Failed to download faculty timetable PDF.');
        } finally {
            setExportingSelected(false);
        }
    };

    const downloadAllFacultyPdfs = async () => {
        setExportingAll(true);
        setError(null);

        try {
            const facultySource = facultyList.length
                ? facultyList
                : (await api.get('/admin/faculty')).data;

            if (!facultySource.length) {
                setError('No faculty records found to download.');
                return;
            }

            const responses = await Promise.all(
                facultySource.map((faculty: FacultyOption) =>
                    api.get('/timetables/faculty', { params: { faculty_id: faculty.id } })
                )
            );

            await downloadAllFacultyTimetablesZip(responses.map((res) => res.data));
        } catch (err: any) {
            console.error('Failed to export all faculty timetables', err);
            setError(err.message || err.response?.data?.detail || 'Failed to download faculty timetable PDFs.');
        } finally {
            setExportingAll(false);
        }
    };

    const entries = data?.entries || [];
    const uniqueTimeRanges = Array.from(new Set(entries.map((entry) => `${entry.start_time}-${entry.end_time}`))).sort();

    const entryMap: Record<string, FacultyTimetableEntry[]> = {};
    entries.forEach((entry) => {
        const key = `${entry.day}-${entry.start_time}-${entry.end_time}`;
        if (!entryMap[key]) {
            entryMap[key] = [];
        }
        entryMap[key].push(entry);
    });

    return (
        <div className="animate-fade-in">
            <div style={{ marginBottom: '2rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <AppLogo size={52} />
                <div>
                    <h1 style={{ fontSize: '2rem', fontWeight: 800, marginBottom: '0.35rem' }}>Faculty Timetable</h1>
                    <p style={{ color: 'var(--text-muted)', margin: 0 }}>
                        Search by faculty name, faculty id code, or choose from the dropdown.
                    </p>
                </div>
            </div>

            <div className="card" style={{ marginBottom: '2rem' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', alignItems: 'end' }}>
                    <div className="input-group" style={{ marginBottom: 0 }}>
                        <label className="input-label">Faculty Name</label>
                        <input
                            className="input-field"
                            value={facultyName}
                            onChange={(e) => setFacultyName(e.target.value)}
                            placeholder="Enter faculty name"
                        />
                    </div>
                    <div className="input-group" style={{ marginBottom: 0 }}>
                        <label className="input-label">Faculty ID</label>
                        <input
                            className="input-field"
                            value={facultyIdCode}
                            onChange={(e) => setFacultyIdCode(e.target.value)}
                            placeholder="Enter faculty id code"
                        />
                    </div>
                    <div className="input-group" style={{ marginBottom: 0 }}>
                        <label className="input-label">Faculty Dropdown</label>
                        <select className="input-field" value={selectedFacultyId} onChange={(e) => handleFacultySelect(e.target.value)}>
                            <option value="">Select Faculty</option>
                            {facultyList.map((faculty) => (
                                <option key={faculty.id} value={faculty.id}>
                                    {faculty.name}{faculty.faculty_id_code ? ` (${faculty.faculty_id_code})` : ''}
                                </option>
                            ))}
                        </select>
                    </div>
                    <button className="btn btn-primary" onClick={searchTimetable} disabled={loading}>
                        <Search size={18} /> {loading ? 'Searching...' : 'View Timetable'}
                    </button>
                    <button className="btn btn-outline" onClick={downloadAllFacultyPdfs} disabled={exportingAll} style={{ background: 'white' }}>
                        {exportingAll ? <RefreshCw className="animate-spin" size={18} /> : <Download size={18} />}
                        {exportingAll ? 'Preparing ZIP...' : 'Download All Faculty PDFs'}
                    </button>
                </div>
            </div>

            {error && (
                <div className="card" style={{ color: 'var(--error-color)', marginBottom: '1rem' }}>
                    {error}
                </div>
            )}

            {data && (
                <>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
                        <div className="card">
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                                <Users size={20} color="var(--primary-color)" />
                                <div>
                                    <div style={{ fontWeight: 700 }}>{data.faculty_name}</div>
                                    <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{data.faculty_id_code || 'No ID'}</div>
                                </div>
                            </div>
                        </div>
                        <div className="card">
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                                <Calendar size={20} color="var(--primary-color)" />
                                <div>
                                    <div style={{ fontWeight: 700 }}>{entries.length}</div>
                                    <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Scheduled Classes</div>
                                </div>
                            </div>
                        </div>
                        <button className="btn btn-outline" onClick={downloadSelectedFacultyPdf} disabled={exportingSelected} style={{ background: 'white', minHeight: '64px', justifyContent: 'center' }}>
                            {exportingSelected ? <RefreshCw className="animate-spin" size={18} /> : <Download size={18} />}
                            {exportingSelected ? 'Preparing PDF...' : 'Download This Faculty'}
                        </button>
                    </div>

                    {entries.length === 0 ? (
                        <div className="card">No timetable entries are assigned to this faculty yet.</div>
                    ) : (
                        <div className="card" style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                    <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
                                        <th style={{ textAlign: 'left', padding: '0.85rem' }}>Day / Time</th>
                                        {uniqueTimeRanges.map((range) => {
                                            const [start, end] = range.split('-');
                                            return (
                                                <th key={range} style={{ textAlign: 'left', padding: '0.85rem', minWidth: '180px' }}>
                                                    {formatTime12Hour(start)} - {formatTime12Hour(end)}
                                                </th>
                                            );
                                        })}
                                    </tr>
                                </thead>
                                <tbody>
                                    {dayOrder.map((day) => (
                                        <tr key={day} style={{ borderBottom: '1px solid var(--border-light)' }}>
                                            <td style={{ padding: '0.85rem', fontWeight: 700 }}>{day}</td>
                                            {uniqueTimeRanges.map((range) => {
                                                const [start, end] = range.split('-');
                                                const slotEntries = entryMap[`${day}-${start}-${end}`] || [];
                                                return (
                                                    <td key={`${day}-${range}`} style={{ padding: '0.85rem', verticalAlign: 'top' }}>
                                                        {slotEntries.length === 0 ? (
                                                            <span style={{ color: 'var(--text-muted)' }}>-</span>
                                                        ) : (
                                                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                                                {slotEntries.map((entry) => (
                                                                    <div key={`${entry.timetable_id}-${entry.subject_id}-${entry.timeslot_id}`} style={{
                                                                        padding: '0.65rem',
                                                                        borderRadius: '0.75rem',
                                                                        background: '#eff6ff',
                                                                        border: '1px solid #bfdbfe'
                                                                    }}>
                                                                        <div style={{ fontWeight: 700, marginBottom: '0.2rem' }}>
                                                                            {entry.subject_code || entry.subject_name}
                                                                        </div>
                                                                        <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                                                                            {entry.subject_name}
                                                                        </div>
                                                                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.35rem' }}>
                                                                            {entry.department_code} {entry.academic_year_name} - Section {entry.section_name}
                                                                        </div>
                                                                    </div>
                                                                ))}
                                                            </div>
                                                        )}
                                                    </td>
                                                );
                                            })}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </>
            )}
        </div>
    );
};

export default AdminFacultyTimetable;
