import React, { useState, useEffect } from 'react';
import api from '../api/axios';
import { Plus, ChevronRight, ChevronDown, Trash2, Layers, Users, Edit2, BookOpen } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { formatTime12Hour } from '../utils/timeFormat';
import TimePicker12 from '../components/TimePicker12';

// Types
interface Section { id: number; name: string; student_count: number; academic_year_id: number; }
interface AcademicYear { id: number; name: string; level: number; department_id: number; sections?: Section[]; }
interface TimeSlot { id: number; department_id?: number | null; day: string; start_time: string; end_time: string; is_break?: boolean; label?: string; }
interface Subject { id: number; name: string; code: string; semester: number; weekly_hours: number; continuous_hours?: number; department_id: number; manual_timeslot_ids?: number[]; is_elective: boolean; elective_group_id?: string; allowed_department_ids?: number[]; }
interface Department { id: number; name: string; code: string; years?: AcademicYear[]; subjects?: Subject[]; }

const Departments = () => {
    const [departments, setDepartments] = useState<Department[]>([]);

    // UI State
    const [expandedDept, setExpandedDept] = useState<number | null>(null);
    const [expandedYear, setExpandedYear] = useState<number | null>(null);

    // Forms
    const [showDeptForm, setShowDeptForm] = useState(false);
    const [editingDeptId, setEditingDeptId] = useState<number | null>(null);
    const [newDept, setNewDept] = useState({ name: '', code: '' });

    const [showYearForm, setShowYearForm] = useState<number | null>(null); // deptId
    const [editingYearId, setEditingYearId] = useState<number | null>(null);
    const [newYear, setNewYear] = useState<{ name: string; level: number | ''; }>({ name: '', level: '' });

    const [showSectionForm, setShowSectionForm] = useState<number | null>(null); // yearId
    const [editingSectionId, setEditingSectionId] = useState<number | null>(null);
    const [newSection, setNewSection] = useState<{ name: string; student_count: number | ''; }>({ name: '', student_count: '' });

    const [showSubjectForm, setShowSubjectForm] = useState<number | null>(null); // deptId
    const [editingSubjectId, setEditingSubjectId] = useState<number | null>(null);
    const [newSubject, setNewSubject] = useState<{
        name: string;
        code: string;
        semester: number | '';
        weekly_hours: number | '';
        continuous_hours: number | '';
        manual_timeslot_ids: number[];
        is_elective: boolean;
        elective_group_id: string;
        allowed_department_ids: number[];
    }>({
        name: '',
        code: '',
        semester: '',
        weekly_hours: '',
        continuous_hours: '',
        manual_timeslot_ids: [],
        is_elective: false,
        elective_group_id: '',
        allowed_department_ids: []
    });
    const [departmentSlots, setDepartmentSlots] = useState<Record<number, TimeSlot[]>>({});
    const [buildingScheduleDept, setBuildingScheduleDept] = useState<number | null>(null);
    const [scheduleForms, setScheduleForms] = useState<Record<number, {
        days: string[];
        start_time: string;
        end_time: string;
        break_start: string;
        break_end: string;
        lunch_start: string;
        lunch_end: string;
    }>>({});
    const workingDays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    const defaultScheduleForm = {
        days: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],
        start_time: '09:00',
        end_time: '15:15',
        break_start: '11:00',
        break_end: '11:15',
        lunch_start: '11:15',
        lunch_end: '12:15',
    };

    useEffect(() => {
        fetchDepartments();
    }, []);

    const fetchDepartments = async () => {
        try {
            const res = await api.get('/admin/departments');
            setDepartments(res.data);
        } catch (err) {
            console.error(err);
            // alert("Failed to fetch departments. Check backend connection.");
        }
    };

    const fetchYears = async (deptId: number) => {
        try {
            const res = await api.get(`/admin/academic-years?department_id=${deptId}`);
            setDepartments(prev => prev.map(d => d.id === deptId ? { ...d, years: res.data } : d));
        } catch (err) { console.error(err); alert("Failed to fetch years."); }
    };

    const fetchSections = async (yearId: number, deptId: number) => {
        try {
            const res = await api.get(`/admin/sections?year_id=${yearId}`);
            setDepartments(prev => prev.map(d => {
                if (d.id !== deptId) return d;
                const updatedYears = d.years?.map(y => y.id === yearId ? { ...y, sections: res.data } : y);
                return { ...d, years: updatedYears };
            }));
        } catch (err) { console.error(err); alert("Failed to fetch sections."); }
    }

    const fetchSubjects = async (deptId: number) => {
        try {
            const res = await api.get(`/admin/subjects?department_id=${deptId}`);
            setDepartments(prev => prev.map(d => d.id === deptId ? { ...d, subjects: res.data } : d));
        } catch (err) { console.error(err); alert("Failed to fetch subjects."); }
    }

    const toggleDept = (id: number) => {
        if (expandedDept === id) {
            setExpandedDept(null);
        } else {
            setExpandedDept(id);
            fetchYears(id);
            fetchSubjects(id);
            fetchDepartmentSlots(id);
            setScheduleForms(prev => ({ ...prev, [id]: prev[id] || defaultScheduleForm }));
        }
    };

    const fetchDepartmentSlots = async (deptId: number) => {
        try {
            const res = await api.get('/admin/timeslots', { params: { department_id: deptId } });
            setDepartmentSlots(prev => ({ ...prev, [deptId]: res.data }));
        } catch (err) {
            console.error("Failed to fetch department slots", err);
        }
    };

    const buildDepartmentSchedule = async (deptId: number) => {
        const form = scheduleForms[deptId] || defaultScheduleForm;
        setBuildingScheduleDept(deptId);
        try {
            const payload = {
                ...form,
                start_time: `${form.start_time}:00`,
                end_time: `${form.end_time}:00`,
                break_start: `${form.break_start}:00`,
                break_end: `${form.break_end}:00`,
                lunch_start: `${form.lunch_start}:00`,
                lunch_end: `${form.lunch_end}:00`,
            };
            const res = await api.post(`/admin/departments/${deptId}/schedule/build`, payload);
            setDepartmentSlots(prev => ({ ...prev, [deptId]: res.data }));
            alert("Department schedule created successfully.");
        } catch (err: any) {
            console.error(err);
            alert(`Failed to build schedule: ${err.response?.data?.detail || err.message}`);
        } finally {
            setBuildingScheduleDept(null);
        }
    };

    const toggleYear = (yearId: number, deptId: number) => {
        if (expandedYear === yearId) {
            setExpandedYear(null);
        } else {
            setExpandedYear(yearId);
            fetchSections(yearId, deptId);
        }
    };

    // Actions
    const saveDept = async () => {
        try {
            if (editingDeptId) {
                await api.put(`/admin/departments/${editingDeptId}`, newDept);
            } else {
                await api.post('/admin/departments', newDept);
            }
            setShowDeptForm(false);
            setEditingDeptId(null);
            setNewDept({ name: '', code: '' });
            fetchDepartments();
        } catch (err: any) {
            console.error(err);
            const msg = err.response?.data?.detail || "Error saving department. Code or Name might be duplicate.";
            alert(`Failed to save department: ${msg}`);
        }
    };

    const startEditDept = (e: React.MouseEvent, dept: Department) => {
        e.stopPropagation();
        setNewDept({ name: dept.name, code: dept.code });
        setEditingDeptId(dept.id);
        setShowDeptForm(true);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    const deleteDept = async (e: React.MouseEvent, id: number) => {
        e.stopPropagation();
        if (!window.confirm("Delete this department? This will delete all years and sections within it.")) return;
        try {
            await api.delete(`/admin/departments/${id}`);
            fetchDepartments();
        } catch (err: any) {
            console.error(err);
            alert(`Failed to delete department: ${err.response?.data?.detail || err.message}`);
        }
    };

    const saveYear = async (deptId: number) => {
        const levelNum = Number(newYear.level);
        if (newYear.level === '' || isNaN(levelNum)) {
            alert("Year Level is required.");
            return;
        }
        try {
            const payload = {
                ...newYear,
                level: levelNum,
                department_id: deptId
            };
            if (editingYearId) {
                await api.put(`/admin/academic-years/${editingYearId}`, payload);
            } else {
                await api.post('/admin/academic-years', payload);
            }
            setShowYearForm(null);
            setEditingYearId(null);
            fetchYears(deptId);
        } catch (err: any) {
            console.error(err);
            alert(`Failed to save year: ${err.response?.data?.detail || "Unknown error"}`);
        }
    };

    const startEditYear = (e: React.MouseEvent, year: AcademicYear, deptId: number) => {
        e.stopPropagation();
        setNewYear({ name: year.name, level: year.level });
        setEditingYearId(year.id);
        setShowYearForm(deptId);
    };

    const deleteYear = async (e: React.MouseEvent, yearId: number, deptId: number) => {
        e.stopPropagation();
        if (!window.confirm("Delete this academic year?")) return;
        try {
            await api.delete(`/admin/academic-years/${yearId}`);
            fetchYears(deptId);
        } catch (err: any) { console.error(err); alert("Error deleting year"); }
    };

    const saveSection = async (yearId: number, deptId: number) => {
        const studentCountNum = newSection.student_count === '' ? 60 : Number(newSection.student_count);
        if (isNaN(studentCountNum)) {
            alert("Student count must be a valid number.");
            return;
        }
        try {
            const payload = {
                ...newSection,
                student_count: studentCountNum,
                academic_year_id: yearId
            };
            if (editingSectionId) {
                await api.put(`/admin/sections/${editingSectionId}`, payload);
            } else {
                await api.post('/admin/sections', payload);
            }
            setShowSectionForm(null);
            setEditingSectionId(null);
            fetchSections(yearId, deptId);
        } catch (err: any) {
            console.error(err);
            alert(`Failed to save section: ${err.response?.data?.detail || "Unknown error"}`);
        }
    };

    const startEditSection = (e: React.MouseEvent, section: Section, yearId: number) => {
        e.stopPropagation();
        setNewSection({ name: section.name, student_count: section.student_count });
        setEditingSectionId(section.id);
        setShowSectionForm(yearId);
    }

    const deleteSection = async (e: React.MouseEvent, sectionId: number, yearId: number, deptId: number) => {
        e.stopPropagation();
        if (!window.confirm("Delete this section?")) return;
        try {
            await api.delete(`/admin/sections/${sectionId}`);
            fetchSections(yearId, deptId);
        } catch (err: any) { console.error(err); alert("Error deleting section"); }
    };

    const saveSubject = async (deptId: number) => {
        if (!newSubject.name.trim()) {
            alert("Subject Name is required.");
            return;
        }
        if (!newSubject.code.trim()) {
            alert("Subject Code is required.");
            return;
        }
        const semesterNum = Number(newSubject.semester);
        if (newSubject.semester === '' || isNaN(semesterNum)) {
            alert("Semester is required.");
            return;
        }
        const weeklyHoursNum = Number(newSubject.weekly_hours);
        if (newSubject.weekly_hours === '' || isNaN(weeklyHoursNum)) {
            alert("Weekly Hours is required.");
            return;
        }
        try {
            const validManualSlotIds = new Set(
                (departmentSlots[deptId] || []).filter(slot => !slot.is_break).map(slot => slot.id)
            );
            const payload = {
                ...newSubject,
                department_id: deptId,
                semester: semesterNum,
                weekly_hours: weeklyHoursNum,
                continuous_hours: Math.min(Math.max(Number(newSubject.continuous_hours) || 1, 1), weeklyHoursNum),
                manual_timeslot_ids: newSubject.manual_timeslot_ids.filter(id => validManualSlotIds.has(id)),
                allowed_department_ids: newSubject.allowed_department_ids
            };
            if (editingSubjectId) {
                await api.put(`/admin/subjects/${editingSubjectId}`, payload);
            } else {
                await api.post('/admin/subjects', payload);
            }
            setShowSubjectForm(null);
            setEditingSubjectId(null);
            fetchSubjects(deptId);
        } catch (err: any) {
            console.error(err);
            alert(`Failed to save subject: ${err.response?.data?.detail || "Check if code is unique"}`);
        }
    };

    const startEditSubject = (sub: Subject, deptId: number) => {
        setNewSubject({
            name: sub.name,
            code: sub.code,
            semester: sub.semester,
            weekly_hours: sub.weekly_hours,
            continuous_hours: sub.continuous_hours || 1,
            manual_timeslot_ids: sub.manual_timeslot_ids || [],
            is_elective: sub.is_elective || false,
            elective_group_id: sub.elective_group_id || '',
            allowed_department_ids: sub.allowed_department_ids || []
        });
        setEditingSubjectId(sub.id);
        setShowSubjectForm(deptId);
    };

    const deleteSubject = async (subId: number, deptId: number) => {
        if (!window.confirm("Delete this subject?")) return;
        try {
            await api.delete(`/admin/subjects/${subId}`);
            fetchSubjects(deptId);
        } catch (err: any) { console.error(err); alert("Error deleting subject"); }
    };

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
                <h1 style={{ fontSize: '2rem', fontWeight: 800 }}>Departments</h1>
                <button className="btn btn-primary" onClick={() => {
                    setEditingDeptId(null);
                    setNewDept({ name: '', code: '' });
                    setShowDeptForm(true);
                }}>
                    <Plus size={20} /> Add Department
                </button>
            </div>

            {/* Department Creation Form */}
            <AnimatePresence>
                {showDeptForm && (
                    <motion.div
                        initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}
                        className="card" style={{ marginBottom: '2rem', borderLeft: '4px solid var(--primary-500)' }}
                    >
                        <h3>{editingDeptId ? 'Edit Department' : 'New Department'}</h3>
                        <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem' }}>
                            <input className="input-field" placeholder="Name (e.g. Computer Science)" value={newDept.name} onChange={e => setNewDept({ ...newDept, name: e.target.value })} />
                            <input className="input-field" placeholder="Code (e.g. CSE)" value={newDept.code} onChange={e => setNewDept({ ...newDept, code: e.target.value })} />
                            <button className="btn btn-primary" onClick={saveDept}>Save</button>
                            <button className="btn" onClick={() => { setShowDeptForm(false); setEditingDeptId(null); }}>Cancel</button>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            <div style={{ display: 'grid', gap: '1rem' }}>
                {departments.map(dept => (
                    <div key={dept.id} className="card" style={{ padding: 0, overflow: 'hidden' }}>
                        <div
                            onClick={() => toggleDept(dept.id)}
                            style={{
                                padding: '1.5rem',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                background: expandedDept === dept.id ? 'var(--primary-50)' : 'transparent'
                            }}
                        >
                            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                <div style={{
                                    width: 40, height: 40, borderRadius: 8,
                                    background: 'var(--primary-100)', color: 'var(--primary-700)',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 'bold'
                                }}>
                                    {dept.code}
                                </div>
                                <span style={{ fontSize: '1.1rem', fontWeight: 600 }}>{dept.name}</span>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <button className="btn" style={{ padding: '0.5rem', color: 'var(--text-muted)' }} onClick={(e) => startEditDept(e, dept)}>
                                    <Edit2 size={18} />
                                </button>
                                <button className="btn" style={{ padding: '0.5rem', color: 'var(--error-color)' }} onClick={(e) => deleteDept(e, dept.id)}>
                                    <Trash2 size={18} />
                                </button>
                                {expandedDept === dept.id ? <ChevronDown /> : <ChevronRight />}
                            </div>
                        </div>

                        <AnimatePresence>
                            {expandedDept === dept.id && (
                                <motion.div
                                    initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }}
                                    style={{ overflow: 'hidden', borderTop: '1px solid var(--border-light)' }}
                                >
                                    <div style={{ padding: '1.5rem', background: '#f8fafc' }}>
                                        {/* --- Department Schedule Builder --- */}
                                        <div style={{ marginBottom: '2rem', background: 'white', border: '1px solid #e2e8f0', borderRadius: 8, padding: '1rem' }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', alignItems: 'flex-start', flexWrap: 'wrap', marginBottom: '1rem' }}>
                                                <div>
                                                    <h4 style={{ margin: 0, color: 'var(--primary-700)', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                                                        <Layers size={18} /> Department Day Schedule
                                                    </h4>
                                                    <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                                                        Set only break and lunch. One-hour class slots are created automatically for this department.
                                                    </p>
                                                </div>
                                                <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                                                    {(departmentSlots[dept.id] || []).length} slots configured
                                                </div>
                                            </div>

                                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.75rem', alignItems: 'end' }}>
                                                <div style={{ gridColumn: '1 / -1' }}>
                                                    <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Working Days</label>
                                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                                                        {workingDays.map(day => {
                                                            const form = scheduleForms[dept.id] || defaultScheduleForm;
                                                            const selected = form.days.includes(day);
                                                            return (
                                                                <button
                                                                    key={day}
                                                                    type="button"
                                                                    className="btn"
                                                                    onClick={() => {
                                                                        const nextDays = selected ? form.days.filter(d => d !== day) : [...form.days, day];
                                                                        setScheduleForms(prev => ({ ...prev, [dept.id]: { ...form, days: nextDays } }));
                                                                    }}
                                                                    style={{
                                                                        padding: '0.3rem 0.65rem',
                                                                        fontSize: '0.78rem',
                                                                        background: selected ? 'var(--primary-500)' : '#f1f5f9',
                                                                        color: selected ? 'white' : 'var(--text-secondary)',
                                                                        borderColor: selected ? 'var(--primary-600)' : '#cbd5e1'
                                                                    }}
                                                                >
                                                                    {day.substring(0, 3)}
                                                                </button>
                                                            );
                                                        })}
                                                    </div>
                                                </div>

                                                {[
                                                    ['start_time', 'College Starts'],
                                                    ['end_time', 'College Ends'],
                                                    ['break_start', 'Break Starts'],
                                                    ['break_end', 'Break Ends'],
                                                    ['lunch_start', 'Lunch Starts'],
                                                    ['lunch_end', 'Lunch Ends'],
                                                ].map(([key, label]) => {
                                                    const form = scheduleForms[dept.id] || defaultScheduleForm;
                                                    return (
                                                        <div key={key}>
                                                            <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>{label}</label>
                                                            <TimePicker12
                                                                value={(form as any)[key]}
                                                                onChange={value => setScheduleForms(prev => ({ ...prev, [dept.id]: { ...form, [key]: value } }))}
                                                            />
                                                        </div>
                                                    );
                                                })}

                                                <button
                                                    className="btn btn-primary"
                                                    onClick={() => buildDepartmentSchedule(dept.id)}
                                                    disabled={buildingScheduleDept === dept.id}
                                                    style={{ minHeight: 42 }}
                                                >
                                                    {buildingScheduleDept === dept.id ? 'Building...' : 'Build Slots'}
                                                </button>
                                            </div>
                                        </div>

                                        {/* --- Subjects Section --- */}
                                        <div style={{ marginBottom: '2rem' }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem', borderBottom: '1px solid #e2e8f0', paddingBottom: '0.5rem' }}>
                                                <h4 style={{ margin: 0, color: 'var(--primary-700)', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                                                    <BookOpen size={18} /> Curriculum (Subjects)
                                                </h4>
                <button className="btn" style={{ fontSize: '0.8rem', padding: '0.2rem 0.6rem' }} onClick={() => {
                                                    setEditingSubjectId(null);
                                                    setNewSubject({
                                                        name: '',
                                                        code: '',
                                                        semester: '',
                                                        weekly_hours: '',
                                                        continuous_hours: '',
                                                        manual_timeslot_ids: [],
                                                        is_elective: false,
                                                        elective_group_id: '',
                                                        allowed_department_ids: []
                                                    });
                                                    setShowSubjectForm(dept.id);
                                                }}>
                                                    <Plus size={16} /> Add Subject
                                                </button>
                                            </div>

                                            {showSubjectForm === dept.id && (
                                                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', background: 'white', padding: '1.5rem', borderRadius: '8px', border: '1px solid var(--primary-200)', marginBottom: '1.5rem' }}>
                                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-end' }}>
                                                        <div className="input-group" style={{ marginBottom: 0, flex: 2, minWidth: '200px' }}>
                                                            <label className="input-label">Subject Name</label>
                                                            <input className="input-field" placeholder="Enter subject name (e.g. Database Systems)" value={newSubject.name} onChange={e => setNewSubject({ ...newSubject, name: e.target.value })} style={{ width: '100%' }} />
                                                        </div>
                                                        <div className="input-group" style={{ marginBottom: 0, flex: 1, minWidth: '120px' }}>
                                                            <label className="input-label">Subject Code</label>
                                                            <input className="input-field" placeholder="Enter code (e.g. CS101)" value={newSubject.code} onChange={e => setNewSubject({ ...newSubject, code: e.target.value })} style={{ width: '100%' }} />
                                                        </div>
                                                        <div className="input-group" style={{ marginBottom: 0, width: '80px' }}>
                                                            <label className="input-label">Semester</label>
                                                            <input
                                                                type="number"
                                                                className="input-field"
                                                                placeholder="Semester"
                                                                value={newSubject.semester}
                                                                onChange={e => {
                                                                    const parsed = parseInt(e.target.value);
                                                                    setNewSubject({ ...newSubject, semester: isNaN(parsed) ? '' : parsed });
                                                                }}
                                                                style={{ width: '100%' }}
                                                            />
                                                        </div>
                                                        <div className="input-group" style={{ marginBottom: 0, width: '100px' }}>
                                                            <label className="input-label">Weekly Hours</label>
                                                            <input
                                                                type="number"
                                                                className="input-field"
                                                                placeholder="Hours"
                                                                value={newSubject.weekly_hours}
                                                                onChange={e => {
                                                                    const parsed = parseInt(e.target.value);
                                                                    const val = isNaN(parsed) ? '' : parsed;
                                                                    setNewSubject({
                                                                        ...newSubject,
                                                                        weekly_hours: val,
                                                                        continuous_hours: val === '' ? '' : Math.min(Number(newSubject.continuous_hours) || 1, val || 1)
                                                                    });
                                                                }}
                                                                style={{ width: '100%' }}
                                                            />
                                                        </div>
                                                        <div className="input-group" style={{ marginBottom: 0, width: '110px' }}>
                                                            <label className="input-label">Back-to-back Hrs</label>
                                                            <input
                                                                type="number"
                                                                className="input-field"
                                                                min="1"
                                                                max={Math.max(Number(newSubject.weekly_hours) || 1, 1)}
                                                                value={newSubject.continuous_hours}
                                                                onChange={e => {
                                                                    const parsed = parseInt(e.target.value);
                                                                    const val = isNaN(parsed) ? '' : parsed;
                                                                    setNewSubject({
                                                                        ...newSubject,
                                                                        continuous_hours: val === '' ? '' : Math.min(Math.max(val || 1, 1), Number(newSubject.weekly_hours) || 1)
                                                                    });
                                                                }}
                                                                placeholder="Max contiguous"
                                                                style={{ width: '100%' }}
                                                            />
                                                        </div>
                                                    </div>
                                                    
                                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1.5rem', alignItems: 'center', padding: '0.75rem', background: '#f8fafc', borderRadius: '6px' }}>
                                                        <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.9rem', fontWeight: 600 }}>
                                                            <input type="checkbox" checked={newSubject.is_elective} onChange={e => setNewSubject({ ...newSubject, is_elective: e.target.checked })} />
                                                            Elective
                                                        </label>
                                                        {newSubject.is_elective && (
                                                            <div className="input-group" style={{ marginBottom: 0, width: '180px' }}>
                                                                <label className="input-label" style={{ fontSize: '0.8rem' }}>Elective Group ID</label>
                                                                <input className="input-field" placeholder="Enter group ID (e.g. PE1)" value={newSubject.elective_group_id} onChange={e => setNewSubject({ ...newSubject, elective_group_id: e.target.value })} style={{ width: '100%', padding: '0.4rem 0.75rem', fontSize: '0.875rem' }} />
                                                            </div>
                                                        )}
                                                    </div>
                                                    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', marginTop: '0.5rem' }}>
                                                        <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>Manual Timeslots (Optional)</label>
                                                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', maxHeight: '120px', overflowY: 'auto', border: '1px solid #e2e8f0', padding: '0.5rem', borderRadius: '4px' }}>
                                                            {(departmentSlots[dept.id] || []).filter(t => !t.is_break).length === 0 ? (
                                                                <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', fontStyle: 'italic' }}>
                                                                    Build the Department Day Schedule first to choose manual class slots.
                                                                </div>
                                                            ) : (
                                                                (departmentSlots[dept.id] || []).filter(t => !t.is_break).map(t => {
                                                                    const isSelected = newSubject.manual_timeslot_ids.includes(t.id);
                                                                    return (
                                                                        <div
                                                                            key={t.id}
                                                                            onClick={() => {
                                                                                if (isSelected) {
                                                                                    setNewSubject({ ...newSubject, manual_timeslot_ids: newSubject.manual_timeslot_ids.filter(id => id !== t.id) });
                                                                                } else {
                                                                                    setNewSubject({ ...newSubject, manual_timeslot_ids: [...newSubject.manual_timeslot_ids, t.id] });
                                                                                }
                                                                            }}
                                                                            style={{
                                                                                fontSize: '0.75rem', padding: '3px 8px', borderRadius: '12px', cursor: 'pointer',
                                                                                background: isSelected ? 'var(--primary-500)' : '#f1f5f9',
                                                                                color: isSelected ? 'white' : 'inherit',
                                                                                border: isSelected ? '1px solid var(--primary-600)' : '1px solid #cbd5e1'
                                                                            }}
                                                                        >
                                                                            {t.day.substring(0, 3)} {formatTime12Hour(t.start_time)}
                                                                        </div>
                                                                    )
                                                                })
                                                            )}
                                                        </div>
                                                    </div>
                                                    
                                                    {/* Other Departments Select */}
                                                    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', marginTop: '0.5rem' }}>
                                                        <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>Available Config: Offered to Other Departments</label>
                                                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', maxHeight: '120px', overflowY: 'auto', border: '1px solid #e2e8f0', padding: '0.5rem', borderRadius: '4px' }}>
                                                            {departments.filter(d => d.id !== dept.id).map(otherDept => {
                                                                const isSelected = newSubject.allowed_department_ids.includes(otherDept.id);
                                                                return (
                                                                    <div
                                                                        key={otherDept.id}
                                                                        onClick={() => {
                                                                            if (isSelected) {
                                                                                setNewSubject({ ...newSubject, allowed_department_ids: newSubject.allowed_department_ids.filter(id => id !== otherDept.id) });
                                                                            } else {
                                                                                setNewSubject({ ...newSubject, allowed_department_ids: [...newSubject.allowed_department_ids, otherDept.id] });
                                                                            }
                                                                        }}
                                                                        style={{
                                                                            fontSize: '0.75rem', padding: '3px 8px', borderRadius: '12px', cursor: 'pointer',
                                                                            background: isSelected ? 'var(--primary-500)' : '#f1f5f9',
                                                                            color: isSelected ? 'white' : 'inherit',
                                                                            border: isSelected ? '1px solid var(--primary-600)' : '1px solid #cbd5e1'
                                                                        }}
                                                                    >
                                                                        {otherDept.code} - {otherDept.name}
                                                                    </div>
                                                                )
                                                            })}
                                                        </div>
                                                    </div>

                                                    <div style={{ width: '100%', marginTop: '0.5rem', display: 'flex', gap: '0.5rem' }}>
                                                        <button className="btn btn-primary" onClick={() => saveSubject(dept.id)}>Save</button>
                                                        <button className="btn" onClick={() => { setShowSubjectForm(null); setEditingSubjectId(null); }}>Cancel</button>
                                                    </div>
                                                </div>
                                            )}

                                            {/* Group Subjects by Semester */}
                                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: '1rem' }}>
                                                {dept.subjects && dept.subjects.length > 0 ? (
                                                    dept.subjects.map(sub => (
                                                        <div key={sub.id} style={{ background: 'white', padding: '1rem', borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
                                                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                                                                <span style={{ fontWeight: 'bold' }}>{sub.name}</span>
                                                                <span style={{ fontSize: '0.8rem', background: '#f1f5f9', padding: '2px 6px', borderRadius: '4px' }}>{sub.code}</span>
                                                            </div>
                                                            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                                                                Semester {sub.semester} • {sub.weekly_hours} hrs/week
                                                                {(sub.continuous_hours || 1) > 1 && (
                                                                    <div style={{ display: 'inline-flex', marginLeft: '0.5rem' }}>
                                                                        <span style={{ fontSize: '0.7rem', background: 'var(--success-light)', color: 'var(--success-color)', padding: '1px 6px', borderRadius: '10px', fontWeight: 600 }}>
                                                                            {sub.continuous_hours} back-to-back
                                                                        </span>
                                                                    </div>
                                                                )}
                                                                {sub.is_elective && (
                                                                    <div style={{ display: 'inline-flex', marginLeft: '0.5rem' }}>
                                                                        <span style={{ fontSize: '0.7rem', background: 'var(--primary-100)', color: 'var(--primary-700)', padding: '1px 6px', borderRadius: '10px', fontWeight: 600 }}>
                                                                            Elective: {sub.elective_group_id}
                                                                        </span>
                                                                    </div>
                                                                )}
                                                                {sub.allowed_department_ids && sub.allowed_department_ids.length > 0 && (
                                                                    <div style={{ display: 'inline-flex', marginLeft: '0.5rem' }}>
                                                                        <span style={{ fontSize: '0.7rem', background: 'var(--warning-100)', color: 'var(--warning-700)', padding: '1px 6px', borderRadius: '10px', fontWeight: 600 }}>
                                                                            Shared ({sub.allowed_department_ids.length})
                                                                        </span>
                                                                    </div>
                                                                )}
                                                                {sub.manual_timeslot_ids && sub.manual_timeslot_ids.length > 0 && (
                                                                    <div style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 4, color: 'var(--warning-color)', fontWeight: 600 }}>
                                                                        <span>📌 Manual Time: {sub.manual_timeslot_ids.length} Scheduled</span>
                                                                    </div>
                                                                )}
                                                            </div>
                                                            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                                                                <button className="btn" style={{ padding: '0.3rem', color: 'var(--text-muted)' }} onClick={() => startEditSubject(sub, dept.id)}>
                                                                    <Edit2 size={14} />
                                                                </button>
                                                                <button className="btn" style={{ padding: '0.3rem', color: 'var(--error-color)' }} onClick={() => deleteSubject(sub.id, dept.id)}>
                                                                    <Trash2 size={14} />
                                                                </button>
                                                            </div>
                                                        </div>
                                                    ))
                                                ) : (
                                                    <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', fontSize: '0.9rem' }}>No subjects added yet.</div>
                                                )}
                                            </div>
                                        </div>

                                        {/* --- Years Section --- */}
                                        <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: '1rem' }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem' }}>
                                                <h4 style={{ margin: 0, color: 'var(--text-muted)' }}>Academic Years & Sections</h4>
                                                <button className="btn" style={{ fontSize: '0.8rem', padding: '0.2rem 0.6rem' }} onClick={() => {
                                                    setEditingYearId(null);
                                                    setNewYear({ name: '', level: '' });
                                                    setShowYearForm(dept.id);
                                                }}>
                                                    <Plus size={16} /> Add Year
                                                </button>
                                            </div>

                                            {showYearForm === dept.id && (
                                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-end', background: 'white', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-color)', marginBottom: '1rem' }}>
                                                    <div className="input-group" style={{ marginBottom: 0, flex: 2, minWidth: '150px' }}>
                                                        <label className="input-label">Academic Year Name</label>
                                                        <input className="input-field" placeholder="Enter year name (e.g. First Year)" value={newYear.name} onChange={e => setNewYear({ ...newYear, name: e.target.value })} style={{ width: '100%' }} />
                                                    </div>
                                                    <div className="input-group" style={{ marginBottom: 0, width: '100px' }}>
                                                        <label className="input-label">Year Level</label>
                                                        <input
                                                            type="number"
                                                            className="input-field"
                                                            placeholder="Level (1-4)"
                                                            value={newYear.level}
                                                            onChange={e => {
                                                                const parsed = parseInt(e.target.value);
                                                                setNewYear({ ...newYear, level: isNaN(parsed) ? '' : parsed });
                                                            }}
                                                            style={{ width: '100%' }}
                                                        />
                                                    </div>
                                                    <div style={{ display: 'flex', gap: '0.5rem', height: '42px', alignItems: 'center' }}>
                                                        <button className="btn btn-primary" onClick={() => saveYear(dept.id)}>Save</button>
                                                        <button className="btn" onClick={() => { setShowYearForm(null); setEditingYearId(null); }}>Cancel</button>
                                                    </div>
                                                </div>
                                            )}

                                            {dept.years?.map(year => (
                                                <div key={year.id} style={{ marginLeft: '1rem', borderLeft: '2px solid var(--border-light)', paddingLeft: '1rem', marginBottom: '0.5rem' }}>
                                                    <div
                                                        onClick={() => toggleYear(year.id, dept.id)}
                                                        style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', padding: '0.5rem 0' }}
                                                    >
                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                                            <Layers size={16} color="var(--primary-500)" />
                                                            <span style={{ fontWeight: 500 }}>{year.name}</span>
                                                        </div>
                                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                                            <button className="btn" style={{ padding: '0.2rem', color: 'var(--text-muted)' }} onClick={(e) => startEditYear(e, year, dept.id)}>
                                                                <Edit2 size={14} />
                                                            </button>
                                                            <button className="btn" style={{ padding: '0.2rem', color: 'var(--error-color)' }} onClick={(e) => deleteYear(e, year.id, dept.id)}>
                                                                <Trash2 size={14} />
                                                            </button>
                                                            {expandedYear === year.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                                        </div>
                                                    </div>

                                                    {expandedYear === year.id && (
                                                        <div style={{ marginLeft: '1.5rem', marginTop: '0.5rem' }}>
                                                            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '0.5rem' }}>
                                                                <small style={{ fontWeight: 'bold', color: 'var(--text-muted)' }}>SECTIONS</small>
                                                                <button
                                                                    style={{ background: 'none', border: 'none', color: 'var(--primary-600)', cursor: 'pointer', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '0.2rem' }}
                                                                    onClick={() => {
                                                                        setEditingSectionId(null);
                                                                        setNewSection({ name: '', student_count: '' });
                                                                        setShowSectionForm(year.id);
                                                                    }}
                                                                >
                                                                    <Plus size={14} /> Add
                                                                </button>
                                                            </div>

                                                            {showSectionForm === year.id && (
                                                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-end', background: '#f1f5f9', padding: '0.75rem', borderRadius: '6px', marginBottom: '0.5rem' }}>
                                                                    <div className="input-group" style={{ marginBottom: 0, width: '130px' }}>
                                                                        <label className="input-label" style={{ fontSize: '0.75rem' }}>Section Name</label>
                                                                        <input className="input-field" placeholder="Enter section (e.g. A)" value={newSection.name} onChange={e => setNewSection({ ...newSection, name: e.target.value })} style={{ width: '100%', padding: '0.5rem 0.75rem', fontSize: '0.85rem' }} />
                                                                    </div>
                                                                    <div className="input-group" style={{ marginBottom: 0, width: '110px' }}>
                                                                        <label className="input-label" style={{ fontSize: '0.75rem' }}>Student Count</label>
                                                                        <input
                                                                            type="number"
                                                                            className="input-field"
                                                                            placeholder="Student count (e.g. 60)"
                                                                            value={newSection.student_count}
                                                                            onChange={e => {
                                                                                const parsed = parseInt(e.target.value);
                                                                                setNewSection({ ...newSection, student_count: isNaN(parsed) ? '' : parsed });
                                                                            }}
                                                                            style={{ width: '100%', padding: '0.5rem 0.75rem', fontSize: '0.85rem' }}
                                                                        />
                                                                    </div>
                                                                    <div style={{ display: 'flex', gap: '0.4rem', height: '34px', alignItems: 'center' }}>
                                                                        <button className="btn btn-primary" style={{ padding: '0.25rem 0.75rem', minHeight: 'unset', height: '34px' }} onClick={() => saveSection(year.id, dept.id)}>Save</button>
                                                                        <button className="btn" style={{ padding: '0.25rem 0.75rem', minHeight: 'unset', height: '34px' }} onClick={() => { setShowSectionForm(null); setEditingSectionId(null); }}>Cancel</button>
                                                                    </div>
                                                                </div>
                                                            )}

                                                            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                                                                {year.sections?.map(sec => (
                                                                    <div key={sec.id} style={{
                                                                        padding: '0.25rem 0.75rem', borderRadius: '1rem',
                                                                        background: 'white', border: '1px solid var(--border-light)',
                                                                        fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '0.5rem'
                                                                    }}>
                                                                        <span>{sec.name}</span>
                                                                        <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', display: 'flex', alignItems: 'center' }}>
                                                                            <Users size={12} style={{ marginRight: 2 }} /> {sec.student_count}
                                                                        </span>
                                                                        <button
                                                                            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, display: 'flex', color: 'var(--text-muted)' }}
                                                                            onClick={(e) => startEditSection(e, sec, year.id)}
                                                                        >
                                                                            <Edit2 size={12} />
                                                                        </button>
                                                                        <button
                                                                            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, display: 'flex', color: 'var(--text-muted)' }}
                                                                            onClick={(e) => deleteSection(e, sec.id, year.id, dept.id)}
                                                                        >
                                                                            <Trash2 size={12} />
                                                                        </button>
                                                                    </div>
                                                                ))}
                                                            </div>
                                                        </div>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default Departments;
