import { useState, useEffect } from 'react';
import axios from 'axios';
import { RefreshCw, Calendar, ChevronDown, Users, Filter, X, Check } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import '../styles/Timetables.css';

// API Configuration
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const axiosInstance = axios.create({
    baseURL: API_URL,
});

axiosInstance.interceptors.request.use((config) => {
    const token = localStorage.getItem('token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

const Timetables = () => {
    // Data State
    const [departments, setDepartments] = useState<any[]>([]);
    const [academicYears, setAcademicYears] = useState<any[]>([]);
    const [sections, setSections] = useState<any[]>([]);
    const [timeSlots, setTimeSlots] = useState<any[]>([]);

    // Selection State
    const [selectedDept, setSelectedDept] = useState('');
    const [selectedYear, setSelectedYear] = useState('');
    const [selectedSection, setSelectedSection] = useState('');
    const [semester, setSemester] = useState(3);

    // Timetable State
    const [timetable, setTimetable] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Initial Load
    useEffect(() => {
        fetchDepartments();
        fetchTimeSlots();
    }, []);

    const fetchDepartments = async () => {
        try {
            const res = await axiosInstance.get('/admin/departments');
            setDepartments(res.data);
        } catch (err) {
            console.error("Error fetching departments", err);
        }
    };

    const fetchTimeSlots = async () => {
        try {
            const res = await axiosInstance.get('/admin/timeslots');
            const sorted = res.data.sort((a: any, b: any) => a.start_time.localeCompare(b.start_time));
            setTimeSlots(sorted);
        } catch (err) {
            console.error("Error fetching time slots", err);
        }
    };

    const handleDeptChange = async (deptId: string) => {
        setSelectedDept(deptId);
        setSelectedYear('');
        setSelectedSection('');
        setAcademicYears([]);
        setSections([]);

        if (!deptId) return;

        try {
            const res = await axiosInstance.get(`/admin/academic-years?department_id=${deptId}`);
            setAcademicYears(res.data);
        } catch (err) {
            console.error(err);
        }
    };

    const handleYearChange = async (yearId: string) => {
        setSelectedYear(yearId);
        setSelectedSection('');
        setSections([]);

        if (!yearId) return;

        try {
            const res = await axiosInstance.get(`/admin/sections?year_id=${yearId}`);
            setSections(res.data);
        } catch (err) {
            console.error(err);
        }
    };

    const generateTimetable = async () => {
        if (!selectedSection) {
            setError("Please select a section.");
            return;
        }

        setLoading(true);
        setError(null);
        setTimetable(null);

        try {
            const res = await axiosInstance.post('/timetables/generate', {
                section_id: parseInt(selectedSection),
                semester: Number(semester)
            });
            setTimetable(res.data);
        } catch (err: any) {
            console.error(err);
            setError(err.response?.data?.detail || "Failed to generate timetable.");
        } finally {
            setLoading(false);
        }
    };

    // Bulk Generation State
    const [bulkGenerating, setBulkGenerating] = useState(false);
    const [bulkResults, setBulkResults] = useState<any>(null);

    // All Timetables State
    const [allTimetables, setAllTimetables] = useState<any[]>([]);
    const [showAllTimetables, setShowAllTimetables] = useState(false);

    const generateAllTimetables = async () => {
        if (!window.confirm("This will generate timetables for ALL sections. Existing timetables will be replaced. Continue?")) {
            return;
        }

        setBulkGenerating(true);
        setBulkResults(null);
        setError(null);

        try {
            const res = await axiosInstance.post('/timetables/generate-all');
            setBulkResults(res.data);
            // Auto-fetch all timetables after generation
            fetchAllTimetables();
        } catch (err: any) {
            console.error(err);
            setError(err.response?.data?.detail || "Failed to generate timetables.");
        } finally {
            setBulkGenerating(false);
        }
    };

    const fetchAllTimetables = async () => {
        try {
            const res = await axiosInstance.get('/timetables/');
            setAllTimetables(res.data);
        } catch (err) {
            console.error("Failed to fetch timetables", err);
        }
    };

    const loadTimetable = async (timetableId: number) => {
        try {
            const res = await axiosInstance.get(`/timetables/${timetableId}`);
            setTimetable(res.data);
            setBulkResults(null);
            setShowAllTimetables(false);
            window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
        } catch (err) {
            console.error("Failed to load timetable", err);
            setError("Failed to load timetable");
        }
    };

    // Grid Rendering Helper
    const renderGrid = () => {
        if (!timetable || !timeSlots.length) return null;

        const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];

        const entryMap: any = {};
        timetable.entries.forEach((entry: any) => {
            entryMap[entry.timeslot_id] = entry;
        });

        const uniqueTimes: any[] = [];
        const seen = new Set();
        timeSlots.forEach((ts: any) => {
            const key = `${ts.start_time}-${ts.end_time}`;
            if (!seen.has(key)) {
                seen.add(key);
                uniqueTimes.push({
                    start: ts.start_time,
                    end: ts.end_time,
                    label: ts.label,
                    is_break: ts.is_break,
                    id: ts.id
                });
            }
        });

        const formatTime = (t: string) => {
            const [h, m] = t.split(':');
            return `${parseInt(h)}:${m}`;
        };

        const formatRange = (start: string, end: string) => {
            const s = formatTime(start);
            const e = formatTime(end);
            return `${s} - ${e}`;
        };

        return (
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="timetable-wrapper"
            >
                {/* Header Information */}
                <div className="timetable-header-info">
                    <div className="info-item">
                        <span className="label">Year</span>
                        <div className="value">
                            {timetable?.section?.academic_year?.name ||
                                academicYears.find((y: any) => y.id == selectedYear)?.name || '-'}
                        </div>
                    </div>
                    <div className="info-item">
                        <span className="label">Semester</span>
                        <div className="value">{timetable?.semester || semester || '-'}</div>
                    </div>
                    <div className="info-item">
                        <span className="label">Section</span>
                        <div className="value">
                            {timetable?.section?.name ||
                                sections.find((s: any) => s.id == selectedSection)?.name || '-'}
                        </div>
                    </div>
                    <div className="info-item">
                        <span className="label">Room</span>
                        <div className="value">
                            {(() => {
                                const roomEntry = timetable?.entries?.find((e: any) => e.room);
                                return roomEntry?.room?.room_number || '-';
                            })()}
                        </div>
                    </div>
                </div>

                <div className="timetable-container">
                    <table className="timetable-grid">
                        <thead>
                            <tr>
                                <th className="header-day">DAY / TIME</th>
                                {uniqueTimes.map((t, idx) => (
                                    <th key={idx} className="header-cell">
                                        <div className="time-range">{formatRange(t.start, t.end)}</div>
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {days.map((day, dayIdx) => (
                                <tr key={day}>
                                    <td className="day-cell">{day.substring(0, 3).toUpperCase()}</td>
                                    {uniqueTimes.map((t, timeIdx) => {
                                        if (t.is_break) {
                                            if (dayIdx === 0) {
                                                return (
                                                    <td key={timeIdx} rowSpan={days.length} className="cell-break">
                                                        <div className="break-text">{t.label?.toUpperCase() || "BREAK"}</div>
                                                    </td>
                                                );
                                            } else {
                                                return null;
                                            }
                                        }

                                        const slot = timeSlots.find((ts: any) => ts.day === day && ts.start_time === t.start);
                                        const entry = slot ? entryMap[slot.id] : null;

                                        return (
                                            <td key={timeIdx} className={`timetable-cell ${entry ? 'cell-filled' : 'cell-empty'}`}>
                                                {entry ? (
                                                    <div className="cell-content">
                                                        <div className="subject-code" title={entry.subject?.name}>
                                                            {entry.subject?.code || 'N/A'}
                                                        </div>
                                                        <div className="faculty-badge" title={entry.faculty?.name || "Unassigned"}>
                                                            {entry.faculty?.name || "Unassigned"}
                                                        </div>
                                                    </div>
                                                ) : (
                                                    <div className="cell-content"></div>
                                                )}
                                            </td>
                                        );
                                    })}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </motion.div>
        );
    };

    return (
        <div className="animate-fade-in page-container">
            <div style={{ marginBottom: '2.5rem' }}>
                <h1 style={{ fontSize: '2rem', fontWeight: 800, margin: '0 0 0.5rem 0', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <div style={{ background: 'var(--primary-100)', color: 'var(--primary-600)', padding: '0.5rem', borderRadius: 'var(--radius-md)' }}>
                        <Calendar size={28} />
                    </div>
                    Timetable Generator
                </h1>
                <p style={{ color: 'var(--text-muted)', fontSize: '1.1rem', margin: 0 }}>
                    Select a target section to generate a conflict-free AI schedule, or batch-generate for all sections.
                </p>
            </div>

            {/* Controls Card */}
            <div className="card controls-card">
                <div className="controls-grid">
                    <div className="input-group" style={{ marginBottom: 0 }}>
                        <label className="input-label">Department</label>
                        <div className="select-wrapper">
                            <select
                                className="input-field"
                                value={selectedDept}
                                onChange={(e) => handleDeptChange(e.target.value)}
                                style={{ width: '100%', boxSizing: 'border-box', appearance: 'none' }}
                            >
                                <option value="">Select</option>
                                {departments.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}
                            </select>
                            <ChevronDown className="select-icon" size={16} />
                        </div>
                    </div>

                    <div className="input-group" style={{ marginBottom: 0 }}>
                        <label className="input-label">Year</label>
                        <div className="select-wrapper">
                            <select
                                className="input-field"
                                value={selectedYear}
                                onChange={(e) => handleYearChange(e.target.value)}
                                disabled={!selectedDept}
                                style={{ width: '100%', boxSizing: 'border-box', appearance: 'none' }}
                            >
                                <option value="">Select Year</option>
                                {academicYears.map((y: any) => <option key={y.id} value={y.id}>{y.name}</option>)}
                            </select>
                            <ChevronDown className="select-icon" size={16} />
                        </div>
                    </div>

                    <div className="input-group" style={{ marginBottom: 0 }}>
                        <label className="input-label">Section</label>
                        <div className="select-wrapper">
                            <select
                                className="input-field"
                                value={selectedSection}
                                onChange={(e) => setSelectedSection(e.target.value)}
                                disabled={!selectedYear}
                                style={{ width: '100%', boxSizing: 'border-box', appearance: 'none' }}
                            >
                                <option value="">Select Section</option>
                                {sections.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
                            </select>
                            <ChevronDown className="select-icon" size={16} />
                        </div>
                    </div>

                    <div className="input-group" style={{ marginBottom: 0 }}>
                        <label className="input-label">Semester</label>
                        <div className="select-wrapper">
                            <input
                                type="number"
                                className="input-field"
                                value={semester}
                                onChange={(e) => setSemester(parseInt(e.target.value))}
                                min="1" max="8"
                                style={{ width: '100%', boxSizing: 'border-box' }}
                            />
                        </div>
                    </div>

                    <button
                        className="btn btn-primary generate-btn"
                        onClick={generateTimetable}
                        disabled={loading || !selectedSection}
                        style={{ height: '42px', marginTop: 'auto' }}
                    >
                        {loading ? <RefreshCw className="animate-spin" size={18} /> : <RefreshCw size={18} />}
                        Generate Standard
                    </button>
                </div>
            </div>

            {/* Bulk Generation / Power Tools Card */}
            <div className="card bulk-actions-card animate-fade-in delay-100">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
                    <div>
                        <h3 style={{ margin: '0 0 0.25rem 0', fontSize: '1.1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <Users size={20} color="var(--primary-600)" />
                            Power Actions
                        </h3>
                        <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                            Automatically generate timetables for ALL sections using available department data. Existing data will be overwritten.
                        </p>
                    </div>
                    <div className="action-buttons">
                        <button
                            className="btn btn-gradient"
                            onClick={generateAllTimetables}
                            disabled={bulkGenerating}
                        >
                            {bulkGenerating ? (
                                <>
                                    <RefreshCw className="animate-spin" size={20} />
                                    Generating All...
                                </>
                            ) : (
                                <>
                                    <Users size={20} />
                                    Generate All Timetables
                                </>
                            )}
                        </button>

                        <button
                            className="btn btn-outline"
                            onClick={() => {
                                fetchAllTimetables();
                                setShowAllTimetables(true);
                            }}
                            style={{ background: 'white' }}
                        >
                            <Filter size={18} />
                            View History
                        </button>
                    </div>
                </div>
            </div>

            {/* View All Timetables Modal */}
            <AnimatePresence>
                {showAllTimetables && (
                    <div className="modal-overlay" onClick={() => setShowAllTimetables(false)}>
                        <motion.div
                            initial={{ scale: 0.9, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.9, opacity: 0 }}
                            className="modal-content card"
                            onClick={(e) => e.stopPropagation()}
                        >
                            <div className="modal-header">
                                <h3>All Generated Timetables</h3>
                                <div style={{ display: 'flex', gap: '0.5rem' }}>
                                    <button
                                        className="btn btn-outline"
                                        style={{ borderColor: 'var(--error-color)', color: 'var(--error-color)', padding: '0.25rem 0.75rem', fontSize: '0.8rem' }}
                                        onClick={async () => {
                                            if (window.confirm("Are you sure you want to clear all timetables history?")) {
                                                try {
                                                    await axiosInstance.delete('/timetables/clear-all');
                                                    fetchAllTimetables();
                                                } catch (e) { console.error("Failed to clear", e) }
                                            }
                                        }}
                                    >
                                        <X size={14} style={{ marginRight: '0.25rem' }} /> Clear History
                                    </button>
                                    <button className="btn-icon" onClick={() => setShowAllTimetables(false)}>
                                        <X size={20} />
                                    </button>
                                </div>
                            </div>

                            <div className="modal-body">
                                {allTimetables.length === 0 ? (
                                    <div className="empty-state">
                                        <p>No timetables found. Generate timetables first.</p>
                                    </div>
                                ) : (
                                    <div className="timetable-list">
                                        {allTimetables.map((tt: any) => (
                                            <div
                                                key={tt.id}
                                                className="timetable-list-item"
                                                onClick={() => loadTimetable(tt.id)}
                                            >
                                                <div>
                                                    <div className="item-title">
                                                        {tt.section?.academic_year?.name || 'Unknown Year'} - Section {tt.section?.name || 'Unknown'}
                                                    </div>
                                                    <div className="item-subtitle">
                                                        Semester {tt.semester} • {tt.entries?.length || 0} classes
                                                    </div>
                                                </div>
                                                <div className="item-action">
                                                    View →
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>

            {/* Bulk Results Summary */}
            {bulkResults && (
                <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="card result-card"
                >
                    <h3 className="result-title">
                        <Check size={24} className="success-icon" />
                        Bulk Generation Complete
                    </h3>

                    <div className="result-stats">
                        <div className="stat-item">
                            <div className="stat-value primary">{bulkResults.total}</div>
                            <div className="stat-label">Total Sections</div>
                        </div>
                        <div className="stat-item bg-success">
                            <div className="stat-value success">{bulkResults.generated}</div>
                            <div className="stat-label">Generated</div>
                        </div>
                        <div className="stat-item bg-error">
                            <div className="stat-value error">{bulkResults.failed}</div>
                            <div className="stat-label">Failed</div>
                        </div>
                    </div>

                    {bulkResults.timetables && bulkResults.timetables.length > 0 && (
                        <div className="generated-list">
                            <h4>Generated Timetables:</h4>
                            <div className="list-container">
                                {bulkResults.timetables.map((tt: any, idx: number) => (
                                    <div
                                        key={idx}
                                        className="generated-item"
                                        onClick={() => loadTimetable(tt.timetable_id)}
                                    >
                                        ✅ {tt.year} - Section {tt.section_name}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </motion.div>
            )}

            {error && (
                <div className="error-banner">
                    <div className="error-dot"></div>
                    {error}
                </div>
            )}

            {/* Timetable View */}
            <AnimatePresence mode='wait'>
                {timetable ? (
                    renderGrid()
                ) : (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="card empty-placeholder"
                    >
                        <div className="icon-circle">
                            <Calendar size={32} />
                        </div>
                        <h3 style={{ margin: '0 0 0.5rem 0', color: 'var(--text-primary)' }}>No Timetable Active</h3>
                        <p style={{ margin: 0 }}>Configure parameters above and click generate to view the schedule.</p>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

export default Timetables;
