import { useState, useEffect } from 'react';
import api from '../api/axios';
import { Plus, Edit2, Trash2, User, BookOpen, Check, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface Subject {
    id: number;
    name: string;
    code: string;
    department_id: number;
    is_elective?: boolean;
    allowed_department_ids?: number[];
}

interface AcademicYear {
    id: number;
    name: string;
    level: number;
    department_id: number;
}

interface Section {
    id: number;
    name: string;
    academic_year_id: number;
}

interface Department {
    id: number;
    name: string;
    code: string;
}

interface Faculty {
    id: number;
    name: string;
    faculty_id_code: string;
    faculty_type: string;
    min_hours_per_week: number;
    max_hours_per_week: number;
    qualified_subjects?: { subject_id: number; preference_level: number; section_ids?: number[] }[];
}

interface SubjectAssignment {
    subject_id: number;
    section_ids: number[];
}

const FacultyManager = () => {
    const [facultyList, setFacultyList] = useState<Faculty[]>([]);
    const [showForm, setShowForm] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);

    // Subject Assignment State
    const [showSubjectModal, setShowSubjectModal] = useState(false);
    const [selectedFaculty, setSelectedFaculty] = useState<Faculty | null>(null);
    const [availableSubjects, setAvailableSubjects] = useState<Subject[]>([]);
    const [availableYears, setAvailableYears] = useState<AcademicYear[]>([]);
    const [availableSections, setAvailableSections] = useState<Section[]>([]);
    const [availableDepartments, setAvailableDepartments] = useState<Department[]>([]);
    const [subjectAssignments, setSubjectAssignments] = useState<SubjectAssignment[]>([]);
    const [selectedYear, setSelectedYear] = useState<number | null>(null);

    const [formData, setFormData] = useState({
        name: '',
        faculty_id_code: '',
        faculty_type: 'ASSISTANT_PROFESSOR',
        min_hours_per_week: 5,
        max_hours_per_week: 18
    });

    useEffect(() => {
        fetchFaculty();
        fetchSubjects();
        fetchYears();
        fetchSections();
        fetchDepartments();
    }, []);

    const fetchSubjects = async () => {
        try {
            const res = await api.get('/admin/subjects');
            setAvailableSubjects(res.data);
        } catch (err) { console.error("Failed to fetch subjects", err); }
    };

    const fetchYears = async () => {
        try {
            const res = await api.get('/admin/academic-years');
            setAvailableYears(res.data);
        } catch (err) { console.error("Failed to fetch years", err); }
    };

    const fetchSections = async () => {
        try {
            const res = await api.get('/admin/sections');
            setAvailableSections(res.data);
        } catch (err) { console.error("Failed to fetch sections", err); }
    };

    const fetchDepartments = async () => {
        try {
            const res = await api.get('/admin/departments');
            setAvailableDepartments(res.data);
        } catch (err) { console.error("Failed to fetch departments", err); }
    };

    const fetchFaculty = async () => {
        try {
            const res = await api.get('/admin/faculty');
            setFacultyList(res.data);
        } catch (err) { console.error(err); }
    };

    const handleSubmit = async () => {
        try {
            if (editingId) {
                await api.put(`/admin/faculty/${editingId}`, formData);
            } else {
                await api.post('/admin/faculty', formData);
            }
            setShowForm(false);
            setEditingId(null);
            resetForm();
            fetchFaculty();
        } catch (err) { console.error(err); alert("Error saving faculty. Check if ID Code is unique."); }
    };

    const resetForm = () => {
        setFormData({
            name: '',
            faculty_id_code: '',
            faculty_type: 'ASSISTANT_PROFESSOR',
            min_hours_per_week: 5,
            max_hours_per_week: 18
        });
    };

    const startEdit = (fac: Faculty) => {
        setFormData({
            name: fac.name,
            faculty_id_code: fac.faculty_id_code || '',
            faculty_type: fac.faculty_type,
            min_hours_per_week: fac.min_hours_per_week,
            max_hours_per_week: fac.max_hours_per_week
        });
        setEditingId(fac.id);
        setShowForm(true);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    const deleteFaculty = async (id: number) => {
        if (!window.confirm("Delete this faculty member?")) return;
        try {
            await api.delete(`/admin/faculty/${id}`);
            fetchFaculty();
        } catch (err) { console.error(err); }
    };

    const openSubjectModal = (fac: Faculty) => {
        setSelectedFaculty(fac);
        setSelectedYear(null);
        const existing = fac.qualified_subjects?.map(qs => ({
            subject_id: qs.subject_id,
            section_ids: qs.section_ids || []
        })) || [];
        setSubjectAssignments(existing);
        setShowSubjectModal(true);
    };

    const toggleSubjectSelection = (subId: number) => {
        setSubjectAssignments(prev => {
            const exists = prev.find(a => a.subject_id === subId);
            if (exists) {
                return prev.filter(a => a.subject_id !== subId);
            } else {
                return [...prev, { subject_id: subId, section_ids: [] }];
            }
        });
    };

    const toggleSectionForSubject = (subId: number, secId: number) => {
        setSubjectAssignments(prev => prev.map(assignment => {
            if (assignment.subject_id === subId) {
                const hasSec = assignment.section_ids.includes(secId);
                return {
                    ...assignment,
                    section_ids: hasSec
                        ? assignment.section_ids.filter(id => id !== secId)
                        : [...assignment.section_ids, secId]
                };
            }
            return assignment;
        }));
    };

    const saveSubjectAssignments = async () => {
        if (!selectedFaculty) return;
        try {
            const payload = subjectAssignments.map(assignment => ({
                subject_id: assignment.subject_id,
                preference_level: 1,
                section_ids: assignment.section_ids.length > 0 ? assignment.section_ids : null
            }));

            await api.post(`/admin/faculty/${selectedFaculty.id}/subjects`, payload);
            setShowSubjectModal(false);
            fetchFaculty();
        } catch (err) { console.error(err); alert("Failed to save assignments"); }
    };

    const filteredSections = selectedYear
        ? availableSections.filter(sec => sec.academic_year_id === selectedYear)
        : availableSections;

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
                <h1 style={{ fontSize: '2rem', fontWeight: 800 }}>Faculty Management</h1>
                <button className="btn btn-primary" onClick={() => {
                    setEditingId(null);
                    resetForm();
                    setShowForm(true);
                }}>
                    <Plus size={20} /> Add Faculty
                </button>
            </div>

            <AnimatePresence>
                {showForm && (
                    <motion.div
                        initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}
                        className="card" style={{ marginBottom: '2rem', borderLeft: '4px solid var(--primary-color)' }}
                    >
                        <h3>{editingId ? 'Edit Faculty' : 'New Faculty Member'}</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '1rem' }}>
                            <div className="input-group">
                                <label className="input-label">Full Name</label>
                                <input className="input-field" value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })} placeholder="e.g. Dr. Jane Doe" />
                            </div>
                            <div className="input-group">
                                <label className="input-label">Faculty ID Code</label>
                                <input className="input-field" value={formData.faculty_id_code} onChange={e => setFormData({ ...formData, faculty_id_code: e.target.value })} placeholder="e.g. FAC001" />
                            </div>

                            <div className="input-group">
                                <label className="input-label">Designation</label>
                                <select className="input-field" value={formData.faculty_type} onChange={e => setFormData({ ...formData, faculty_type: e.target.value })}>
                                    <option value="PROFESSOR">Professor</option>
                                    <option value="ASSISTANT_PROFESSOR">Assistant Professor</option>
                                    <option value="LAB_INSTRUCTOR">Lab Instructor</option>
                                    <option value="GUEST">Guest</option>
                                </select>
                            </div>

                            <div style={{ display: 'flex', gap: '1rem' }}>
                                <div className="input-group" style={{ flex: 1 }}>
                                    <label className="input-label">Min Hours/Week</label>
                                    <input type="number" className="input-field" value={formData.min_hours_per_week} onChange={e => setFormData({ ...formData, min_hours_per_week: parseInt(e.target.value) })} />
                                </div>
                                <div className="input-group" style={{ flex: 1 }}>
                                    <label className="input-label">Max Hours/Week</label>
                                    <input type="number" className="input-field" value={formData.max_hours_per_week} onChange={e => setFormData({ ...formData, max_hours_per_week: parseInt(e.target.value) })} />
                                </div>
                            </div>
                        </div>
                        <div style={{ marginTop: '1rem', display: 'flex', gap: '1rem' }}>
                            <button className="btn btn-primary" onClick={handleSubmit}>Save Profile</button>
                            <button className="btn" onClick={() => setShowForm(false)}>Cancel</button>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Subject & Section Assignment Modal */}
            <AnimatePresence>
                {showSubjectModal && selectedFaculty && (
                    <div style={{
                        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
                        background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
                    }} onClick={() => setShowSubjectModal(false)}>
                        <motion.div
                            initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.9, opacity: 0 }}
                            className="card" style={{ width: '750px', maxHeight: '85vh', display: 'flex', flexDirection: 'column', padding: 0 }}
                            onClick={e => e.stopPropagation()}
                        >
                            <div style={{ padding: '1.5rem', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <h3 style={{ margin: 0 }}>Assign Subjects & Sections to {selectedFaculty.name}</h3>
                                <button className="btn" onClick={() => setShowSubjectModal(false)}><X size={20} /></button>
                            </div>

                            <div style={{ padding: '1.5rem', overflowY: 'auto', flex: 1 }}>
                                <p style={{ marginBottom: '1rem', color: 'var(--text-secondary)' }}>
                                    Select subjects and specific year-section combinations this faculty will teach.
                                </p>

                                {/* Year Filter */}
                                <div style={{ marginBottom: '1.5rem', padding: '1rem', background: 'var(--background-color)', borderRadius: '8px' }}>
                                    <label style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.5rem', display: 'block' }}>
                                        Filter Sections by Year:
                                    </label>
                                    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                                        <button
                                            onClick={() => setSelectedYear(null)}
                                            style={{
                                                padding: '0.5rem 1rem',
                                                borderRadius: '6px',
                                                border: `2px solid ${selectedYear === null ? 'var(--primary-color)' : 'var(--border-color)'}`,
                                                background: selectedYear === null ? 'var(--primary-color)' : 'white',
                                                color: selectedYear === null ? 'white' : 'var(--text-primary)',
                                                cursor: 'pointer',
                                                fontSize: '0.875rem',
                                                fontWeight: 500
                                            }}
                                        >
                                            All Years
                                        </button>
                                        {availableYears.map(year => {
                                            const dept = availableDepartments.find(d => d.id === year.department_id);
                                            const label = dept ? `${dept.code} - ${year.name}` : year.name;
                                            return (
                                                <button
                                                    key={year.id}
                                                    onClick={() => setSelectedYear(year.id)}
                                                    style={{
                                                        padding: '0.5rem 1rem',
                                                        borderRadius: '6px',
                                                        border: `2px solid ${selectedYear === year.id ? 'var(--primary-color)' : 'var(--border-color)'}`,
                                                        background: selectedYear === year.id ? 'var(--primary-color)' : 'white',
                                                        color: selectedYear === year.id ? 'white' : 'var(--text-primary)',
                                                        cursor: 'pointer',
                                                        fontSize: '0.875rem',
                                                        fontWeight: 500
                                                    }}
                                                >
                                                    {label}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>

                                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                                    {availableSubjects.map(sub => {
                                        const assignment = subjectAssignments.find(a => a.subject_id === sub.id);
                                        const isSelected = !!assignment;

                                        return (
                                            <div key={sub.id} style={{
                                                padding: '1rem',
                                                borderRadius: '8px',
                                                border: `2px solid ${isSelected ? 'var(--primary-color)' : 'var(--border-color)'}`,
                                                background: isSelected ? '#f0f4ff' : 'white'
                                            }}>
                                                <div
                                                    onClick={() => toggleSubjectSelection(sub.id)}
                                                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}
                                                >
                                                    <div>
                                                        <div style={{ fontWeight: 600, fontSize: '1rem' }}>{sub.name}</div>
                                                        <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                                                            {sub.code} • {availableDepartments.find(d => d.id === sub.department_id)?.code || 'No Dept'}
                                                        </div>
                                                    </div>
                                                    {isSelected && <Check size={20} color="var(--primary-color)" />}
                                                </div>

                                                {isSelected ? (
                                                    <div style={{ marginTop: '0.75rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-color)' }}>
                                                        <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>
                                                            Assign to Sections {selectedYear ? `(${availableYears.find(y => y.id === selectedYear)?.name})` : ''}:
                                                        </div>
                                                        {filteredSections.length > 0 ? (
                                                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                                                                {filteredSections.filter(sec => {
                                                                    const yearInfo = availableYears.find(y => y.id === sec.academic_year_id);
                                                                    if (!yearInfo) return false;
                                                                    
                                                                    const isPrimaryDept = yearInfo.department_id === sub.department_id;
                                                                    const isAllowedDept = sub.allowed_department_ids?.includes(yearInfo.department_id) || false;
                                                                    
                                                                    return isPrimaryDept || isAllowedDept;
                                                                }).map(sec => {
                                                                    const sectionSelected = assignment.section_ids.includes(sec.id);
                                                                    const yearInfo = availableYears.find(y => y.id === sec.academic_year_id);
                                                                    const deptInfo = yearInfo ? availableDepartments.find(d => d.id === yearInfo.department_id) : null;
                                                                    const sectionLabel = deptInfo ? `${deptInfo.code} - ${yearInfo?.name} - Section ${sec.name}` : `${yearInfo?.name} - Section ${sec.name}`;

                                                                    return (
                                                                        <div
                                                                            key={sec.id}
                                                                            onClick={() => toggleSectionForSubject(sub.id, sec.id)}
                                                                            style={{
                                                                                padding: '0.4rem 0.8rem',
                                                                                borderRadius: '6px',
                                                                                border: `1.5px solid ${sectionSelected ? 'var(--primary-color)' : 'var(--border-color)'}`,
                                                                                background: sectionSelected ? 'var(--primary-color)' : 'white',
                                                                                color: sectionSelected ? 'white' : 'var(--text-primary)',
                                                                                cursor: 'pointer',
                                                                                fontSize: '0.85rem',
                                                                                fontWeight: 500,
                                                                                transition: 'all 0.2s'
                                                                            }}
                                                                        >
                                                                            {sectionLabel}
                                                                        </div>
                                                                    );
                                                                })}
                                                            </div>
                                                        ) : (
                                                            <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                                                                No sections available for selected year
                                                            </div>
                                                        )}
                                                        {assignment.section_ids.length === 0 && (
                                                            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.5rem', fontStyle: 'italic' }}>
                                                                No sections selected - available for all sections
                                                            </div>
                                                        )}
                                                    </div>
                                                ) : (
                                                    <div style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                                                        Click anywhere on this card to select this subject and assign specific sections.
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>

                            <div style={{ padding: '1.5rem', borderTop: '1px solid var(--border-color)', display: 'flex', justifyContent: 'flex-end', gap: '1rem' }}>
                                <button className="btn" onClick={() => setShowSubjectModal(false)}>Cancel</button>
                                <button className="btn btn-primary" onClick={saveSubjectAssignments}>
                                    Save Assignments ({subjectAssignments.length})
                                </button>
                            </div>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1.5rem' }}>
                {facultyList.map(fac => (
                    <div key={fac.id} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                                <div style={{
                                    width: 48, height: 48, borderRadius: '50%', background: 'var(--background-color)',
                                    color: 'var(--primary-color)', display: 'flex', alignItems: 'center', justifyContent: 'center'
                                }}>
                                    <User size={24} />
                                </div>
                                <div>
                                    <div style={{ fontWeight: 700, fontSize: '1.1rem' }}>{fac.name}</div>
                                    <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        <span style={{ background: '#f1f5f9', padding: '2px 6px', borderRadius: 4 }}>{fac.faculty_id_code || 'No ID'}</span>
                                        <span>•</span>
                                        <span>{fac.faculty_type.replace('_', ' ')}</span>
                                    </div>
                                </div>
                            </div>
                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                                <button className="btn" title="Assign Subjects" style={{ padding: '0.4rem', color: 'var(--secondary-color)', background: 'var(--background-color)' }} onClick={() => openSubjectModal(fac)}>
                                    <BookOpen size={16} />
                                </button>
                                <button className="btn" style={{ padding: '0.4rem', color: 'var(--text-secondary)' }} onClick={() => startEdit(fac)}>
                                    <Edit2 size={16} />
                                </button>
                                <button className="btn" style={{ padding: '0.4rem', color: 'var(--error-color)' }} onClick={() => deleteFaculty(fac.id)}>
                                    <Trash2 size={16} />
                                </button>
                            </div>
                        </div>

                        <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', fontSize: '0.9rem' }}>
                            <div style={{ textAlign: 'center' }}>
                                <div style={{ fontWeight: 700, color: 'var(--primary-color)' }}>{fac.min_hours_per_week}h</div>
                                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Min Load</div>
                            </div>
                            <div style={{ textAlign: 'center' }}>
                                <div style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{fac.max_hours_per_week}h</div>
                                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Max Load</div>
                            </div>
                            <div style={{ textAlign: 'center' }}>
                                <div style={{ fontWeight: 700, color: 'var(--secondary-color)' }}>{fac.qualified_subjects?.length || 0}</div>
                                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Subjects</div>
                            </div>
                            <div style={{ textAlign: 'center' }}>
                                <div style={{ fontWeight: 700, color: '#10b981' }}>Active</div>
                                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Status</div>
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default FacultyManager;
