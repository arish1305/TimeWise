import { useState, useEffect } from 'react';
import axios from 'axios';
import { Edit3, RefreshCw, Lock, Cpu, Plus, Trash2, ChevronDown } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import '../styles/ManualTimetableEditor.css';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const axiosInstance = axios.create({ baseURL: API_URL });
axiosInstance.interceptors.request.use((config) => {
    const token = localStorage.getItem('token');
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
});

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];

const ManualTimetableEditor = () => {
    // Data
    const [departments, setDepartments] = useState<any[]>([]);
    const [academicYears, setAcademicYears] = useState<any[]>([]);
    const [sections, setSections] = useState<any[]>([]);
    const [timeSlots, setTimeSlots] = useState<any[]>([]);
    const [subjects, setSubjects] = useState<any[]>([]);
    const [faculty, setFaculty] = useState<any[]>([]);
    const [rooms, setRooms] = useState<any[]>([]);

    // Selection
    const [selectedDept, setSelectedDept] = useState('');
    const [selectedYear, setSelectedYear] = useState('');
    const [selectedSection, setSelectedSection] = useState('');
    const [semester, setSemester] = useState(3);

    // Timetable
    const [timetable, setTimetable] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [regenerating, setRegenerating] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Modal
    const [modalOpen, setModalOpen] = useState(false);
    const [modalSlot, setModalSlot] = useState<any>(null);
    const [modalEntry, setModalEntry] = useState<any>(null);
    const [modalForm, setModalForm] = useState({
        subject_id: '',
        faculty_id: '',
        room_id: '',
        is_locked: true
    });
    const [saving, setSaving] = useState(false);

    // Init
    useEffect(() => {
        fetchDepartments();
        fetchTimeSlots();
        fetchRooms();
    }, []);

    const fetchDepartments = async () => {
        try {
            const res = await axiosInstance.get('/admin/departments');
            setDepartments(res.data);
        } catch (err) { console.error(err); }
    };

    const fetchTimeSlots = async () => {
        try {
            const res = await axiosInstance.get('/admin/timeslots');
            setTimeSlots(res.data.sort((a: any, b: any) => a.start_time.localeCompare(b.start_time)));
        } catch (err) { console.error(err); }
    };

    const fetchRooms = async () => {
        try {
            const res = await axiosInstance.get('/admin/rooms');
            setRooms(res.data);
        } catch (err) { console.error(err); }
    };

    const handleDeptChange = async (deptId: string) => {
        setSelectedDept(deptId);
        setSelectedYear('');
        setSelectedSection('');
        setAcademicYears([]);
        setSections([]);
        setTimetable(null);
        setSubjects([]);
        setFaculty([]);

        if (!deptId) return;
        try {
            const [yearsRes, subjectsRes, facultyRes] = await Promise.all([
                axiosInstance.get(`/admin/academic-years?department_id=${deptId}`),
                axiosInstance.get(`/admin/subjects?department_id=${deptId}`),
                axiosInstance.get('/admin/faculty')
            ]);
            setAcademicYears(yearsRes.data);
            setSubjects(subjectsRes.data);
            setFaculty(facultyRes.data);
        } catch (err) { console.error(err); }
    };

    const handleYearChange = async (yearId: string) => {
        setSelectedYear(yearId);
        setSelectedSection('');
        setSections([]);
        setTimetable(null);

        if (!yearId) return;
        try {
            const res = await axiosInstance.get(`/admin/sections?year_id=${yearId}`);
            setSections(res.data);
        } catch (err) { console.error(err); }
    };

    const handleSectionChange = async (sectionId: string) => {
        setSelectedSection(sectionId);
        setTimetable(null);
        if (!sectionId) return;
        await loadTimetable(parseInt(sectionId));
    };

    const loadTimetable = async (sectionId: number) => {
        setLoading(true);
        setError(null);
        try {
            const res = await axiosInstance.get('/timetables/');
            const match = res.data.find(
                (tt: any) => tt.section_id === sectionId && tt.semester === semester
            );
            setTimetable(match || null);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    // Grid helpers
    const getUniqueTimes = () => {
        const unique: any[] = [];
        const seen = new Set();
        timeSlots.forEach((ts: any) => {
            const key = `${ts.start_time}-${ts.end_time}`;
            if (!seen.has(key)) {
                seen.add(key);
                unique.push({
                    start: ts.start_time,
                    end: ts.end_time,
                    label: ts.label,
                    is_break: ts.is_break,
                });
            }
        });
        return unique;
    };

    const formatTime = (t: string) => {
        const [h, m] = t.split(':');
        return `${parseInt(h)}:${m}`;
    };

    const getEntryForCell = (day: string, startTime: string) => {
        if (!timetable?.entries) return null;
        const slot = timeSlots.find((ts: any) => ts.day === day && ts.start_time === startTime);
        if (!slot) return null;
        return timetable.entries.find((e: any) => e.timeslot_id === slot.id) || null;
    };

    const getTimeslotId = (day: string, startTime: string) => {
        const slot = timeSlots.find((ts: any) => ts.day === day && ts.start_time === startTime);
        return slot?.id || null;
    };

    // Modal
    const openModalForEmpty = (day: string, startTime: string) => {
        const tsId = getTimeslotId(day, startTime);
        if (!tsId) return;
        setModalSlot({ day, startTime, timeslot_id: tsId });
        setModalEntry(null);
        // Filter subjects to current semester
        setModalForm({ subject_id: '', faculty_id: '', room_id: '', is_locked: true });
        setModalOpen(true);
    };

    const openModalForEntry = (entry: any) => {
        setModalEntry(entry);
        setModalSlot(null);
        setModalForm({
            subject_id: String(entry.subject_id),
            faculty_id: entry.faculty_id ? String(entry.faculty_id) : '',
            room_id: entry.room_id ? String(entry.room_id) : '',
            is_locked: entry.is_locked
        });
        setModalOpen(true);
    };

    const closeModal = () => {
        setModalOpen(false);
        setModalSlot(null);
        setModalEntry(null);
        setError(null);
    };

    const handleSave = async () => {
        if (!modalForm.subject_id) return;
        setSaving(true);
        setError(null);

        try {
            if (modalEntry) {
                // Update existing
                await axiosInstance.put(`/timetables/manual-entry/${modalEntry.id}`, {
                    subject_id: parseInt(modalForm.subject_id),
                    faculty_id: modalForm.faculty_id ? parseInt(modalForm.faculty_id) : null,
                    room_id: modalForm.room_id ? parseInt(modalForm.room_id) : null,
                    is_locked: modalForm.is_locked
                });
            } else {
                // Create new
                await axiosInstance.post('/timetables/manual-entry', {
                    section_id: parseInt(selectedSection),
                    semester: semester,
                    subject_id: parseInt(modalForm.subject_id),
                    faculty_id: modalForm.faculty_id ? parseInt(modalForm.faculty_id) : null,
                    room_id: modalForm.room_id ? parseInt(modalForm.room_id) : null,
                    timeslot_id: modalSlot.timeslot_id,
                    is_locked: modalForm.is_locked
                });
            }
            closeModal();
            await loadTimetable(parseInt(selectedSection));
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to save entry');
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async () => {
        if (!modalEntry) return;
        setSaving(true);
        try {
            await axiosInstance.delete(`/timetables/manual-entry/${modalEntry.id}`);
            closeModal();
            await loadTimetable(parseInt(selectedSection));
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to delete entry');
        } finally {
            setSaving(false);
        }
    };

    const handleRegenerate = async () => {
        if (!selectedSection) return;
        if (!window.confirm('This will regenerate all AI-generated slots while keeping your locked entries. Continue?')) return;

        setRegenerating(true);
        setError(null);
        try {
            const res = await axiosInstance.post('/timetables/regenerate', {
                section_id: parseInt(selectedSection),
                semester: semester
            });
            setTimetable(res.data);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Regeneration failed');
        } finally {
            setRegenerating(false);
        }
    };

    const semesterSubjects = subjects.filter((s: any) => s.semester === semester);
    const uniqueTimes = getUniqueTimes();

    return (
        <div className="editor-page animate-fade-in">
            <div className="page-header">
                <h1>
                    <span className="icon-wrapper"><Edit3 size={24} /></span>
                    Schedule Editor
                </h1>
                <p>Manually assign and lock slots, then let the AI fill the rest.</p>
            </div>

            {/* Controls */}
            <div className="card">
                <div className="editor-controls">
                    <div className="input-group">
                        <label className="input-label">Department</label>
                        <div className="select-wrapper">
                            <select className="input-field" value={selectedDept} onChange={e => handleDeptChange(e.target.value)}>
                                <option value="">Select Department</option>
                                {departments.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}
                            </select>
                            <ChevronDown className="select-icon" size={16} />
                        </div>
                    </div>

                    <div className="input-group">
                        <label className="input-label">Year</label>
                        <div className="select-wrapper">
                            <select className="input-field" value={selectedYear} onChange={e => handleYearChange(e.target.value)} disabled={!selectedDept}>
                                <option value="">Select Year</option>
                                {academicYears.map((y: any) => <option key={y.id} value={y.id}>{y.name}</option>)}
                            </select>
                            <ChevronDown className="select-icon" size={16} />
                        </div>
                    </div>

                    <div className="input-group">
                        <label className="input-label">Section</label>
                        <div className="select-wrapper">
                            <select className="input-field" value={selectedSection} onChange={e => handleSectionChange(e.target.value)} disabled={!selectedYear}>
                                <option value="">Select Section</option>
                                {sections.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
                            </select>
                            <ChevronDown className="select-icon" size={16} />
                        </div>
                    </div>

                    <div className="input-group">
                        <label className="input-label">Semester</label>
                        <input type="number" className="input-field" value={semester} onChange={e => setSemester(parseInt(e.target.value))} min="1" max="8" style={{ width: 80 }} />
                    </div>
                </div>

                {/* Legend + Actions */}
                {selectedSection && (
                    <>
                        <div className="editor-legend">
                            <div className="legend-item"><div className="legend-swatch locked" /><span>Manual / Locked</span></div>
                            <div className="legend-item"><div className="legend-swatch ai" /><span>AI Generated</span></div>
                            <div className="legend-item"><div className="legend-swatch empty" /><span>Empty (click to assign)</span></div>
                        </div>
                        <div className="editor-actions">
                            <button className="btn-regenerate" onClick={handleRegenerate} disabled={regenerating}>
                                {regenerating ? <RefreshCw className="animate-spin" size={16} /> : <Cpu size={16} />}
                                {regenerating ? 'Regenerating...' : 'Regenerate Remaining'}
                            </button>
                        </div>
                    </>
                )}
            </div>

            {error && !modalOpen && (
                <div className="editor-error">⚠️ {error}</div>
            )}

            {/* Grid */}
            {loading ? (
                <div className="card editor-empty">
                    <RefreshCw className="animate-spin" size={32} style={{ margin: '0 auto', color: 'var(--primary-color)' }} />
                    <p>Loading timetable...</p>
                </div>
            ) : selectedSection ? (
                <div className="editor-grid-wrapper">
                    <div className="editor-grid-container">
                        <table className="editor-grid">
                            <thead>
                                <tr>
                                    <th>DAY / TIME</th>
                                    {uniqueTimes.map((t, i) => (
                                        <th key={i}>{formatTime(t.start)} - {formatTime(t.end)}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {DAYS.map((day, dayIdx) => (
                                    <tr key={day}>
                                        <td className="day-label">{day.substring(0, 3).toUpperCase()}</td>
                                        {uniqueTimes.map((t, tIdx) => {
                                            if (t.is_break) {
                                                if (dayIdx === 0) {
                                                    return (
                                                        <td key={tIdx} rowSpan={DAYS.length} className="editor-cell cell-break-editor">
                                                            {t.label?.toUpperCase() || 'BREAK'}
                                                        </td>
                                                    );
                                                }
                                                return null;
                                            }

                                            const entry = getEntryForCell(day, t.start);

                                            if (entry) {
                                                const isLocked = entry.is_locked;
                                                const isAdmin = entry.created_by === 'ADMIN';
                                                return (
                                                    <td
                                                        key={tIdx}
                                                        className={`editor-cell ${isLocked || isAdmin ? 'cell-locked' : 'cell-ai'}`}
                                                        onClick={() => openModalForEntry(entry)}
                                                    >
                                                        <div className="editor-cell-content">
                                                            {isLocked ? (
                                                                <Lock size={12} className="cell-lock-icon" />
                                                            ) : (
                                                                <Cpu size={12} className="cell-ai-icon" />
                                                            )}
                                                            <span className="cell-subject">{entry.subject?.code || 'N/A'}</span>
                                                            <span className="cell-faculty-name">{entry.faculty?.name || 'Unassigned'}</span>
                                                        </div>
                                                    </td>
                                                );
                                            }

                                            return (
                                                <td
                                                    key={tIdx}
                                                    className="editor-cell cell-clickable"
                                                    onClick={() => openModalForEmpty(day, t.start)}
                                                >
                                                    <div className="cell-plus"><Plus size={20} /></div>
                                                </td>
                                            );
                                        })}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            ) : (
                <div className="card editor-empty">
                    <div className="icon-circle"><Edit3 size={32} /></div>
                    <p>Select a department, year, and section to start editing</p>
                </div>
            )}

            {/* Assignment Modal */}
            <AnimatePresence>
                {modalOpen && (
                    <div className="editor-modal-overlay" onClick={closeModal}>
                        <motion.div
                            initial={{ scale: 0.9, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.9, opacity: 0 }}
                            className="editor-modal"
                            onClick={e => e.stopPropagation()}
                        >
                            <h3>{modalEntry ? 'Edit Assignment' : 'Assign Slot'}</h3>
                            <p className="modal-subtitle">
                                {modalSlot
                                    ? `${modalSlot.day} • ${formatTime(modalSlot.startTime)}`
                                    : modalEntry?.timeslot
                                        ? `${modalEntry.timeslot.day} • ${formatTime(modalEntry.timeslot.start_time)}`
                                        : ''}
                            </p>

                            <div className="input-group">
                                <label className="input-label">Subject</label>
                                <select
                                    value={modalForm.subject_id}
                                    onChange={e => setModalForm({ ...modalForm, subject_id: e.target.value })}
                                >
                                    <option value="">Select Subject</option>
                                    {semesterSubjects.map((s: any) => (
                                        <option key={s.id} value={s.id}>{s.code} — {s.name}</option>
                                    ))}
                                </select>
                            </div>

                            <div className="input-group">
                                <label className="input-label">Faculty</label>
                                <select
                                    value={modalForm.faculty_id}
                                    onChange={e => setModalForm({ ...modalForm, faculty_id: e.target.value })}
                                >
                                    <option value="">None / Unassigned</option>
                                    {faculty.map((f: any) => (
                                        <option key={f.id} value={f.id}>{f.name}</option>
                                    ))}
                                </select>
                            </div>

                            <div className="input-group">
                                <label className="input-label">Room</label>
                                <select
                                    value={modalForm.room_id}
                                    onChange={e => setModalForm({ ...modalForm, room_id: e.target.value })}
                                >
                                    <option value="">None</option>
                                    {rooms.map((r: any) => (
                                        <option key={r.id} value={r.id}>{r.room_number} (Cap: {r.capacity})</option>
                                    ))}
                                </select>
                            </div>

                            <label className="lock-toggle">
                                <input
                                    type="checkbox"
                                    checked={modalForm.is_locked}
                                    onChange={e => setModalForm({ ...modalForm, is_locked: e.target.checked })}
                                />
                                <Lock size={16} />
                                <span>Lock this slot (AI cannot modify)</span>
                            </label>

                            {error && modalOpen && (
                                <div className="editor-error" style={{ marginTop: 0, marginBottom: '0.5rem' }}>⚠️ {error}</div>
                            )}

                            <div className="modal-actions">
                                {modalEntry && (
                                    <button className="btn-modal-delete" onClick={handleDelete} disabled={saving}>
                                        <Trash2 size={14} style={{ marginRight: 4 }} /> Delete
                                    </button>
                                )}
                                <button className="btn-modal-cancel" onClick={closeModal}>Cancel</button>
                                <button className="btn-modal-save" onClick={handleSave} disabled={saving || !modalForm.subject_id}>
                                    {saving ? 'Saving...' : modalEntry ? 'Update' : 'Assign'}
                                </button>
                            </div>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>
        </div>
    );
};

export default ManualTimetableEditor;
