import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Calendar, RefreshCw, Filter, ChevronDown } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

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
            const hour = parseInt(h);
            return `${hour}.${m}`;
        };

        const formatRange = (start: string, end: string) => {
            const s = formatTime(start);
            const e = formatTime(end);
            const endHour = parseInt(end.split(':')[0]);
            const ampm = endHour >= 12 ? 'pm' : 'am';
            return `${s}-${e}${ampm}`;
        };

        const cellStyle: React.CSSProperties = {
            border: '1px solid var(--text-primary)',
            padding: '8px',
            textAlign: 'center',
            position: 'relative',
        };

        const headerStyle: React.CSSProperties = {
            ...cellStyle,
            backgroundColor: 'var(--secondary-color)',
            color: 'white',
            fontWeight: 'bold',
            textTransform: 'uppercase',
            fontSize: '0.85rem'
        };

        return (
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="card"
                style={{ marginTop: '2rem', padding: '0', overflow: 'hidden' }}
            >
                {/* Header Information */}
                <div style={{
                    padding: '1.5rem',
                    borderBottom: '2px solid var(--text-primary)',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    backgroundColor: '#fff'
                }}>
                    <div><span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block' }}>Year</span><strong style={{ fontSize: '1.1rem' }}>{academicYears.find((y: any) => y.id == selectedYear)?.name || '-'}</strong></div>
                    <div><span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block' }}>Semester</span><strong style={{ fontSize: '1.1rem' }}>{semester || '-'}</strong></div>
                    <div><span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block' }}>Batch</span><strong style={{ fontSize: '1.1rem' }}>2023-2027</strong></div>
                    <div><span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block' }}>Section</span><strong style={{ fontSize: '1.1rem' }}>{sections.find((s: any) => s.id == selectedSection)?.name || '-'}</strong></div>
                    <div><span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block' }}>Hall</span><strong style={{ fontSize: '1.1rem' }}>363</strong></div>
                </div>

                <div style={{ overflowX: 'auto', padding: '1rem' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', backgroundColor: 'white' }}>
                        <thead>
                            <tr>
                                <th style={{ ...headerStyle, width: '120px' }}>
                                    DAY/TIMING
                                </th>
                                {uniqueTimes.map((t, idx) => (
                                    <th key={idx} style={headerStyle}>
                                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                                            <span>{formatRange(t.start, t.end)}</span>
                                        </div>
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {days.map((day, dayIdx) => (
                                <tr key={day}>
                                    <td style={{ ...cellStyle, fontWeight: 'bold', backgroundColor: 'var(--background-color)' }}>
                                        {day}
                                    </td>
                                    {uniqueTimes.map((t, timeIdx) => {
                                        if (t.is_break) {
                                            if (dayIdx === 0) {
                                                return (
                                                    <td key={timeIdx} rowSpan={days.length} style={{ ...cellStyle, backgroundColor: '#f1f5f9', verticalAlign: 'middle' }}>
                                                        <div style={{
                                                            writingMode: 'vertical-lr',
                                                            textOrientation: 'upright',
                                                            letterSpacing: '0.2em',
                                                            height: '100%',
                                                            margin: '0 auto',
                                                            fontWeight: 'bold',
                                                            color: 'var(--text-secondary)'
                                                        }}>
                                                            {t.label?.toUpperCase() || "BREAK"}
                                                        </div>
                                                    </td>
                                                );
                                            } else {
                                                return null;
                                            }
                                        }

                                        const slot = timeSlots.find((ts: any) => ts.day === day && ts.start_time === t.start);
                                        const entry = slot ? entryMap[slot.id] : null;

                                        return (
                                            <td key={timeIdx} style={{ ...cellStyle, height: '80px', verticalAlign: 'middle' }}>
                                                {entry ? (
                                                    <div style={{
                                                        display: 'flex',
                                                        flexDirection: 'column',
                                                        alignItems: 'center',
                                                        justifyContent: 'center',
                                                        height: '100%'
                                                    }}>
                                                        <span style={{ fontWeight: 'bold', color: 'var(--primary-color)', fontSize: '1rem', marginBottom: '4px' }}>{entry.subject?.code}</span>
                                                        <span style={{
                                                            fontSize: '0.75rem',
                                                            color: '#fff',
                                                            backgroundColor: 'var(--primary-color)',
                                                            padding: '2px 8px',
                                                            borderRadius: '12px'
                                                        }}>{entry.faculty?.name || "TBD"}</span>
                                                    </div>
                                                ) : (
                                                    <span style={{ color: 'var(--border-color)' }}>-</span>
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
        <div className="animate-fade-in">
            <div style={{ marginBottom: '2rem' }}>
                <h1 style={{ fontSize: '1.875rem', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                    <span style={{
                        display: 'inline-flex',
                        padding: '0.5rem',
                        backgroundColor: 'var(--primary-color)',
                        color: 'white',
                        borderRadius: '0.5rem',
                        boxShadow: '0 4px 6px -1px rgba(99, 102, 241, 0.3)'
                    }}>
                        <Calendar size={24} />
                    </span>
                    Timetable Generator
                </h1>
                <p style={{ color: 'var(--text-secondary)' }}>Generate and manage academic schedules with ease.</p>
            </div>

            {/* Controls Card */}
            <div className="card" style={{ marginBottom: '2rem' }}>
                <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                    gap: '1.5rem',
                    alignItems: 'end'
                }}>
                    <div className="input-group" style={{ marginBottom: 0 }}>
                        <label className="input-label">Department</label>
                        <div style={{ position: 'relative' }}>
                            <select
                                className="input-field"
                                style={{ width: '100%', appearance: 'none', cursor: 'pointer' }}
                                value={selectedDept}
                                onChange={(e) => handleDeptChange(e.target.value)}
                            >
                                <option value="">Select Department</option>
                                {departments.map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}
                            </select>
                            <ChevronDown size={16} style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none', color: 'var(--text-secondary)' }} />
                        </div>
                    </div>

                    <div className="input-group" style={{ marginBottom: 0 }}>
                        <label className="input-label">Year</label>
                        <div style={{ position: 'relative' }}>
                            <select
                                className="input-field"
                                style={{ width: '100%', appearance: 'none', cursor: 'pointer' }}
                                value={selectedYear}
                                onChange={(e) => handleYearChange(e.target.value)}
                                disabled={!selectedDept}
                            >
                                <option value="">Select Year</option>
                                {academicYears.map((y: any) => <option key={y.id} value={y.id}>{y.name}</option>)}
                            </select>
                            <ChevronDown size={16} style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none', color: 'var(--text-secondary)' }} />
                        </div>
                    </div>

                    <div className="input-group" style={{ marginBottom: 0 }}>
                        <label className="input-label">Section</label>
                        <div style={{ position: 'relative' }}>
                            <select
                                className="input-field"
                                style={{ width: '100%', appearance: 'none', cursor: 'pointer' }}
                                value={selectedSection}
                                onChange={(e) => setSelectedSection(e.target.value)}
                                disabled={!selectedYear}
                            >
                                <option value="">Select Section</option>
                                {sections.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
                            </select>
                            <ChevronDown size={16} style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none', color: 'var(--text-secondary)' }} />
                        </div>
                    </div>

                    <div className="input-group" style={{ marginBottom: 0 }}>
                        <label className="input-label">Semester</label>
                        <input
                            type="number"
                            className="input-field"
                            value={semester}
                            onChange={(e) => setSemester(parseInt(e.target.value))}
                            min="1" max="8"
                        />
                    </div>

                    <button
                        className="btn btn-primary"
                        onClick={generateTimetable}
                        disabled={loading || !selectedSection}
                        style={{ height: '42px', opacity: (loading || !selectedSection) ? 0.7 : 1 }}
                    >
                        {loading ? <RefreshCw className="animate-spin" size={18} /> : <RefreshCw size={18} />}
                        Generate
                    </button>
                </div>
            </div>

            {error && (
                <div style={{
                    padding: '1rem',
                    backgroundColor: '#fef2f2',
                    color: 'var(--error-color)',
                    borderRadius: '0.5rem',
                    border: '1px solid #fecaca',
                    marginBottom: '1.5rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem'
                }}>
                    <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--error-color)' }}></div>
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
                        className="card"
                        style={{
                            padding: '4rem',
                            textAlign: 'center',
                            borderStyle: 'dashed',
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            gap: '1rem',
                            color: 'var(--text-secondary)'
                        }}
                    >
                        <div style={{
                            padding: '1rem',
                            backgroundColor: 'var(--background-color)',
                            borderRadius: '50%',
                            display: 'inline-flex'
                        }}>
                            <Filter size={32} style={{ opacity: 0.5 }} />
                        </div>
                        <p style={{ fontWeight: 500 }}>Configure parameters above to generate a timetable</p>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

export default Timetables;
