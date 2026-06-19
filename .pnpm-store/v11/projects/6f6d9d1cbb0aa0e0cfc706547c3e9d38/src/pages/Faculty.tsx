import { useState, useEffect } from 'react';
import api from '../api/axios';
import { Plus, Edit2, Trash2, User, BookOpen, Check, X, Upload, Download, Search } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { formatTimeRange12Hour } from '../utils/timeFormat';

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
    departments?: Department[];
    qualified_subjects?: { subject_id: number; preference_level: number; section_ids?: number[] }[];
}

interface SubjectAssignment {
    subject_id: number;
    section_ids: number[];
}

interface BulkFacultyRow {
    name: string;
    faculty_id_code: string;
    faculty_type: string;
    min_hours_per_week: number;
    max_hours_per_week: number;
    department_codes: string;
}

type AvailabilityStatus = 'AVAILABLE' | 'PREFERRED' | 'UNAVAILABLE';

interface FacultyAvailabilityEntry {
    timeslot_id: number;
    status: AvailabilityStatus;
    day: string;
    start_time: string;
    end_time: string;
    department_id?: number | null;
}

const FacultyManager = () => {
    const [facultyList, setFacultyList] = useState<Faculty[]>([]);
    const [showForm, setShowForm] = useState(false);
    const [showBulkPanel, setShowBulkPanel] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [appliedSearchQuery, setAppliedSearchQuery] = useState('');

    // Subject Assignment State
    const [showSubjectModal, setShowSubjectModal] = useState(false);
    const [selectedFaculty, setSelectedFaculty] = useState<Faculty | null>(null);
    const [availableSubjects, setAvailableSubjects] = useState<Subject[]>([]);
    const [availableYears, setAvailableYears] = useState<AcademicYear[]>([]);
    const [availableSections, setAvailableSections] = useState<Section[]>([]);
    const [availableDepartments, setAvailableDepartments] = useState<Department[]>([]);
    const [subjectAssignments, setSubjectAssignments] = useState<SubjectAssignment[]>([]);
    const [selectedYear, setSelectedYear] = useState<number | null>(null);
    const [selectedModalDept, setSelectedModalDept] = useState<number | null>(null);
    const [modalSearchQuery, setModalSearchQuery] = useState('');
    const [appliedModalSearchQuery, setAppliedModalSearchQuery] = useState('');
    const [availabilityEntries, setAvailabilityEntries] = useState<FacultyAvailabilityEntry[]>([]);
    const [availabilityLoading, setAvailabilityLoading] = useState(false);
    const [availabilitySavingKey, setAvailabilitySavingKey] = useState<string | null>(null);

    const [formData, setFormData] = useState({
        name: '',
        faculty_id_code: '',
        faculty_type: 'ASSISTANT_PROFESSOR',
        min_hours_per_week: 5,
        max_hours_per_week: 18,
        department_ids: [] as number[]
    });
    const [bulkRows, setBulkRows] = useState<BulkFacultyRow[]>([createEmptyBulkRow()]);
    const [bulkFile, setBulkFile] = useState<File | null>(null);
    const [bulkLoading, setBulkLoading] = useState(false);

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
            max_hours_per_week: 18,
            department_ids: []
        });
    };

    const startEdit = (fac: Faculty) => {
        setFormData({
            name: fac.name,
            faculty_id_code: fac.faculty_id_code || '',
            faculty_type: fac.faculty_type,
            min_hours_per_week: fac.min_hours_per_week,
            max_hours_per_week: fac.max_hours_per_week,
            department_ids: fac.departments?.map(dept => dept.id) || []
        });
        setEditingId(fac.id);
        setShowForm(true);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    function createEmptyBulkRow(): BulkFacultyRow {
        return {
            name: '',
            faculty_id_code: '',
            faculty_type: 'ASSISTANT_PROFESSOR',
            min_hours_per_week: 5,
            max_hours_per_week: 18,
            department_codes: ''
        };
    }

    const updateBulkRow = (index: number, field: keyof BulkFacultyRow, value: string | number) => {
        setBulkRows(prev => prev.map((row, rowIndex) => (
            rowIndex === index ? { ...row, [field]: value } : row
        )));
    };

    const addBulkRow = () => {
        setBulkRows(prev => [...prev, createEmptyBulkRow()]);
    };

    const removeBulkRow = (index: number) => {
        setBulkRows(prev => prev.length === 1 ? prev : prev.filter((_, rowIndex) => rowIndex !== index));
    };

    const resetBulkPanel = () => {
        setBulkRows([createEmptyBulkRow()]);
        setBulkFile(null);
    };

    const handleBulkResult = async (result: { created_count: number; errors: string[] }) => {
        await fetchFaculty();
        const messages = [
            `Created ${result.created_count} faculty record${result.created_count === 1 ? '' : 's'}.`
        ];
        if (result.errors.length > 0) {
            messages.push('', 'Some rows were skipped:', ...result.errors);
        }
        alert(messages.join('\n'));
    };

    const submitManualBulk = async () => {
        const rows = bulkRows
            .filter(row => row.name.trim() || row.faculty_id_code.trim() || row.department_codes.trim())
            .map(row => ({
                ...row,
                faculty_id_code: row.faculty_id_code.trim() || null,
                department_codes: row.department_codes
                    .split(/[,;|]/)
                    .map(code => code.trim().toUpperCase())
                    .filter(Boolean)
            }));

        if (rows.length === 0) {
            alert('Add at least one faculty row before bulk saving.');
            return;
        }

        setBulkLoading(true);
        try {
            const res = await api.post('/admin/faculty/bulk', { rows });
            await handleBulkResult(res.data);
            resetBulkPanel();
        } catch (err: any) {
            console.error(err);
            alert(err.response?.data?.detail || 'Failed to save bulk faculty data.');
        } finally {
            setBulkLoading(false);
        }
    };

    const uploadBulkFile = async () => {
        if (!bulkFile) {
            alert('Choose a CSV or XLSX file first.');
            return;
        }

        const formPayload = new FormData();
        formPayload.append('file', bulkFile);

        setBulkLoading(true);
        try {
            const res = await api.post('/admin/faculty/bulk-upload', formPayload, {
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            await handleBulkResult(res.data);
            resetBulkPanel();
        } catch (err: any) {
            console.error(err);
            alert(err.response?.data?.detail || 'Failed to upload faculty file.');
        } finally {
            setBulkLoading(false);
        }
    };

    const downloadTemplate = async () => {
        try {
            const res = await api.get('/admin/faculty/template', { responseType: 'blob' });
            const blob = new Blob([res.data], { type: res.headers['content-type'] || 'application/octet-stream' });
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = 'faculty_bulk_template.xlsx';
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(url);
        } catch (err) {
            console.error(err);
            alert('Failed to download faculty template.');
        }
    };

    const deleteFaculty = async (id: number) => {
        if (!window.confirm("Delete this faculty member?")) return;
        try {
            await api.delete(`/admin/faculty/${id}`);
            fetchFaculty();
        } catch (err) { console.error(err); }
    };

    const fetchFacultyAvailability = async (facultyId: number) => {
        setAvailabilityLoading(true);
        try {
            const res = await api.get(`/faculty/${facultyId}/availability`);
            setAvailabilityEntries(res.data.entries || []);
        } catch (err) {
            console.error("Failed to fetch faculty availability", err);
            setAvailabilityEntries([]);
        } finally {
            setAvailabilityLoading(false);
        }
    };

    const openSubjectModal = (fac: Faculty) => {
        setSelectedFaculty(fac);
        setSelectedYear(null);
        setSelectedModalDept(null);
        setModalSearchQuery('');
        setAppliedModalSearchQuery('');
        const existing = fac.qualified_subjects?.map(qs => ({
            subject_id: qs.subject_id,
            section_ids: qs.section_ids || []
        })) || [];
        setSubjectAssignments(existing);
        fetchFacultyAvailability(fac.id);
        setShowSubjectModal(true);
    };

    const closeSubjectModal = () => {
        setShowSubjectModal(false);
        setSelectedYear(null);
        setSelectedModalDept(null);
        setModalSearchQuery('');
        setAppliedModalSearchQuery('');
    };

    const cycleAvailabilityStatus = (status: AvailabilityStatus): AvailabilityStatus => {
        if (status === 'AVAILABLE') return 'PREFERRED';
        if (status === 'PREFERRED') return 'UNAVAILABLE';
        return 'AVAILABLE';
    };

    const availabilityCellStatus = (entries: FacultyAvailabilityEntry[]): AvailabilityStatus => {
        if (entries.some(entry => entry.status === 'UNAVAILABLE')) return 'UNAVAILABLE';
        if (entries.some(entry => entry.status === 'PREFERRED')) return 'PREFERRED';
        return 'AVAILABLE';
    };

    const updateAvailabilityCell = async (cellEntries: FacultyAvailabilityEntry[], cellKey: string) => {
        if (!selectedFaculty || cellEntries.length === 0) return;
        const nextStatus = cycleAvailabilityStatus(availabilityCellStatus(cellEntries));
        const updates = cellEntries.map(entry => ({
            timeslot_id: entry.timeslot_id,
            status: nextStatus
        }));

        setAvailabilityEntries(prev => prev.map(entry => (
            updates.some(update => update.timeslot_id === entry.timeslot_id)
                ? { ...entry, status: nextStatus }
                : entry
        )));

        setAvailabilitySavingKey(cellKey);
        try {
            await api.post(`/faculty/${selectedFaculty.id}/availability`, { entries: updates });
        } catch (err: any) {
            console.error("Failed to update faculty availability", err);
            alert(err.response?.data?.detail || "Failed to update availability");
            fetchFacultyAvailability(selectedFaculty.id);
        } finally {
            setAvailabilitySavingKey(null);
        }
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
            closeSubjectModal();
            fetchFaculty();
        } catch (err) { console.error(err); alert("Failed to save assignments"); }
    };

    const filteredSections = selectedYear
        ? availableSections.filter(sec => sec.academic_year_id === selectedYear)
        : availableSections;
    const availabilityDays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    const availabilityRows = Array.from(
        new Map(
            availabilityEntries
                .filter(entry => availabilityDays.includes(entry.day))
                .map(entry => [`${entry.start_time}-${entry.end_time}`, { start_time: entry.start_time, end_time: entry.end_time }])
        ).values()
    ).sort((a, b) => a.start_time.localeCompare(b.start_time));

    const availabilityStyles: Record<AvailabilityStatus, { label: string; background: string; color: string; border: string }> = {
        AVAILABLE: { label: 'Available', background: '#f8fafc', color: '#475569', border: '#e2e8f0' },
        PREFERRED: { label: 'Preferred', background: '#dcfce7', color: '#166534', border: '#86efac' },
        UNAVAILABLE: { label: 'Unavailable', background: '#fee2e2', color: '#991b1b', border: '#fecaca' },
    };

    const filteredFaculty = facultyList.filter(fac => {
        const query = appliedSearchQuery.trim().toLowerCase();
        if (!query) return true;

        const nameMatch = fac.name.toLowerCase().includes(query);
        const codeMatch = fac.faculty_id_code?.toLowerCase().includes(query) || false;
        const typeMatch = fac.faculty_type.toLowerCase().replace('_', ' ').includes(query);
        const deptMatch = fac.departments?.some(dept =>
            dept.code.toLowerCase().includes(query) || dept.name.toLowerCase().includes(query)
        ) || false;

        return nameMatch || codeMatch || typeMatch || deptMatch;
    });

    const filteredSubjectsInModal = availableSubjects.filter(sub => {
        if (selectedModalDept !== null && sub.department_id !== selectedModalDept) {
            return false;
        }
        if (appliedModalSearchQuery.trim() !== '') {
            const q = appliedModalSearchQuery.toLowerCase();
            const nameMatch = sub.name.toLowerCase().includes(q);
            const codeMatch = sub.code.toLowerCase().includes(q);
            if (!nameMatch && !codeMatch) return false;
        }
        return true;
    });

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
                <h1 style={{ fontSize: '2rem', fontWeight: 800 }}>Faculty Management</h1>
                <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                    <button className="btn" onClick={() => setShowBulkPanel(prev => !prev)}>
                        <Upload size={18} /> {showBulkPanel ? 'Hide Bulk Onboarding' : 'Bulk Onboarding'}
                    </button>
                    <button className="btn btn-primary" onClick={() => {
                        setEditingId(null);
                        resetForm();
                        setShowForm(true);
                    }}>
                        <Plus size={20} /> Add Faculty
                    </button>
                </div>
            </div>

            {/* Search Bar */}
            <div className="card" style={{ marginBottom: '2rem', padding: '1rem' }}>
                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                    <div style={{ position: 'relative', flex: 1 }}>
                        <Search
                            size={18}
                            style={{
                                position: 'absolute',
                                left: '1rem',
                                top: '50%',
                                transform: 'translateY(-50%)',
                                color: 'var(--text-muted)'
                            }}
                        />
                        <input
                            type="text"
                            className="input-field"
                            placeholder="Search by faculty name, ID, designation, or department..."
                            value={searchQuery}
                            onChange={e => {
                                setSearchQuery(e.target.value);
                                if (e.target.value === '') {
                                    setAppliedSearchQuery('');
                                }
                            }}
                            onKeyDown={e => {
                                if (e.key === 'Enter') {
                                    setAppliedSearchQuery(searchQuery);
                                }
                            }}
                            style={{
                                width: '100%',
                                paddingLeft: '2.75rem',
                                height: '2.75rem',
                                margin: 0
                            }}
                        />
                        {searchQuery && (
                            <button
                                onClick={() => {
                                    setSearchQuery('');
                                    setAppliedSearchQuery('');
                                }}
                                style={{
                                    position: 'absolute',
                                    right: '1rem',
                                    top: '50%',
                                    transform: 'translateY(-50%)',
                                    background: 'none',
                                    border: 'none',
                                    cursor: 'pointer',
                                    color: 'var(--text-muted)',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    padding: 0
                                }}
                            >
                                <X size={16} />
                            </button>
                        )}
                    </div>
                    <button
                        className="btn btn-primary"
                        onClick={() => setAppliedSearchQuery(searchQuery)}
                        style={{ height: '2.75rem', whiteSpace: 'nowrap' }}
                    >
                        <Search size={18} /> Search
                    </button>
                </div>
            </div>

            <AnimatePresence>
                {showBulkPanel && (
                    <motion.div
                        initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}
                        className="card" style={{ marginBottom: '2rem', borderLeft: '4px solid var(--secondary-color)' }}
                    >
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap', alignItems: 'flex-start' }}>
                            <div>
                                <h3 style={{ marginBottom: '0.35rem' }}>Bulk Faculty Onboarding</h3>
                                <p style={{ margin: 0, color: 'var(--text-secondary)' }}>
                                    Add multiple faculty manually below, or upload a `.csv` or `.xlsx` file using the template format.
                                </p>
                            </div>
                            <button className="btn" onClick={downloadTemplate}>
                                <Download size={18} /> Download Example Excel
                            </button>
                        </div>

                        <div style={{ marginTop: '1.5rem', padding: '1rem', border: '1px solid var(--border-color)', borderRadius: '8px', background: 'var(--background-color)' }}>
                            <label className="input-label" style={{ marginBottom: '0.5rem', display: 'block' }}>Upload Faculty File (CSV or Excel)</label>
                            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
                                <input
                                    type="file"
                                    accept=".csv,.xlsx"
                                    onChange={e => setBulkFile(e.target.files?.[0] || null)}
                                />
                                <button className="btn btn-primary" onClick={uploadBulkFile} disabled={bulkLoading}>
                                    <Upload size={16} /> {bulkLoading ? 'Uploading...' : 'Upload File'}
                                </button>
                                {bulkFile && (
                                    <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                                        {bulkFile.name}
                                    </span>
                                )}
                            </div>
                        </div>

                        <div style={{ marginTop: '1.5rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                                <h4 style={{ margin: 0 }}>Manual Bulk Entry</h4>
                                <button className="btn" onClick={addBulkRow}>
                                    <Plus size={16} /> Add Row
                                </button>
                            </div>

                            <div style={{ overflowX: 'auto', paddingBottom: '0.5rem', width: '100%' }}>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', minWidth: '950px' }}>
                                    {bulkRows.map((row, index) => (
                                        <div key={index} style={{
                                            display: 'grid',
                                            gridTemplateColumns: 'minmax(180px, 1.4fr) minmax(120px, 1fr) minmax(150px, 1fr) 110px 110px minmax(180px, 1.2fr) 44px',
                                            gap: '0.75rem',
                                            alignItems: 'end',
                                            padding: '0.9rem',
                                            border: '1px solid var(--border-color)',
                                            borderRadius: '8px',
                                            background: 'white'
                                        }}>
                                            <div className="input-group" style={{ marginBottom: 0 }}>
                                                <label className="input-label">Name</label>
                                                <input className="input-field" placeholder="Enter faculty name" value={row.name} onChange={e => updateBulkRow(index, 'name', e.target.value)} />
                                            </div>
                                            <div className="input-group" style={{ marginBottom: 0 }}>
                                                <label className="input-label">ID Code</label>
                                                <input className="input-field" placeholder="Enter ID code" value={row.faculty_id_code} onChange={e => updateBulkRow(index, 'faculty_id_code', e.target.value)} />
                                            </div>
                                            <div className="input-group" style={{ marginBottom: 0 }}>
                                                <label className="input-label">Designation</label>
                                                <input className="input-field" placeholder="Enter designation (e.g. Professor)" value={row.faculty_type} onChange={e => updateBulkRow(index, 'faculty_type', e.target.value)} />
                                            </div>
                                            <div className="input-group" style={{ marginBottom: 0 }}>
                                                <label className="input-label">Min</label>
                                                <input type="number" className="input-field" placeholder="Min load" value={row.min_hours_per_week} onChange={e => updateBulkRow(index, 'min_hours_per_week', parseInt(e.target.value) || 0)} />
                                            </div>
                                            <div className="input-group" style={{ marginBottom: 0 }}>
                                                <label className="input-label">Max</label>
                                                <input type="number" className="input-field" placeholder="Max load" value={row.max_hours_per_week} onChange={e => updateBulkRow(index, 'max_hours_per_week', parseInt(e.target.value) || 0)} />
                                            </div>
                                            <div className="input-group" style={{ marginBottom: 0 }}>
                                                <label className="input-label">Department Codes</label>
                                                <input className="input-field" placeholder="Enter department codes (e.g. CSE, ECE)" value={row.department_codes} onChange={e => updateBulkRow(index, 'department_codes', e.target.value)} />
                                            </div>
                                            <button className="btn" style={{ padding: '0.65rem', color: 'var(--error-color)' }} onClick={() => removeBulkRow(index)} title="Remove row">
                                                <Trash2 size={16} />
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            <div style={{ marginTop: '1rem', display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                                <button className="btn btn-primary" onClick={submitManualBulk} disabled={bulkLoading}>
                                    <Check size={16} /> {bulkLoading ? 'Saving...' : 'Save Bulk Faculty'}
                                </button>
                                <button className="btn" onClick={resetBulkPanel}>Reset Rows</button>
                                <div style={{ alignSelf: 'center', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                                    Department codes can be separated with commas, semicolons, or pipes.
                                </div>
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

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
                                <input className="input-field" value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })} placeholder="Enter full name (e.g. Dr. Jane Doe)" />
                            </div>
                            <div className="input-group">
                                <label className="input-label">Faculty ID Code</label>
                                <input className="input-field" value={formData.faculty_id_code} onChange={e => setFormData({ ...formData, faculty_id_code: e.target.value })} placeholder="Enter faculty ID code (e.g. FAC001)" />
                            </div>

                            <div className="input-group">
                                <label className="input-label">Designation</label>
                                <input className="input-field" placeholder="Enter designation (e.g. Professor)" value={formData.faculty_type} onChange={e => setFormData({ ...formData, faculty_type: e.target.value })} />
                            </div>

                            <div style={{ display: 'flex', gap: '1rem' }}>
                                <div className="input-group" style={{ flex: 1 }}>
                                    <label className="input-label">Min Hours/Week</label>
                                    <input type="number" className="input-field" placeholder="Enter min load (e.g. 5)" value={formData.min_hours_per_week} onChange={e => setFormData({ ...formData, min_hours_per_week: parseInt(e.target.value) })} />
                                </div>
                                <div className="input-group" style={{ flex: 1 }}>
                                    <label className="input-label">Max Hours/Week</label>
                                    <input type="number" className="input-field" placeholder="Enter max load (e.g. 18)" value={formData.max_hours_per_week} onChange={e => setFormData({ ...formData, max_hours_per_week: parseInt(e.target.value) })} />
                                </div>
                            </div>

                            <div className="input-group" style={{ gridColumn: '1 / -1' }}>
                                <label className="input-label">Departments</label>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                                    {availableDepartments.map(dept => {
                                        const selected = formData.department_ids.includes(dept.id);
                                        return (
                                            <button
                                                key={dept.id}
                                                type="button"
                                                onClick={() => setFormData(prev => ({
                                                    ...prev,
                                                    department_ids: selected
                                                        ? prev.department_ids.filter(id => id !== dept.id)
                                                        : [...prev.department_ids, dept.id]
                                                }))}
                                                style={{
                                                    padding: '0.45rem 0.8rem',
                                                    borderRadius: '999px',
                                                    border: `1.5px solid ${selected ? 'var(--primary-color)' : 'var(--border-color)'}`,
                                                    background: selected ? 'var(--primary-color)' : 'white',
                                                    color: selected ? 'white' : 'var(--text-primary)',
                                                    cursor: 'pointer',
                                                    fontSize: '0.85rem',
                                                    fontWeight: 600
                                                }}
                                            >
                                                {dept.code}
                                            </button>
                                        );
                                    })}
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
                    }} onClick={closeSubjectModal}>
                        <motion.div
                            initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.9, opacity: 0 }}
                            className="card" style={{ width: '750px', maxHeight: '85vh', display: 'flex', flexDirection: 'column', padding: 0 }}
                            onClick={e => e.stopPropagation()}
                        >
                            <div style={{ padding: '1.5rem', borderBottom: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <h3 style={{ margin: 0 }}>Assign Subjects & Sections to {selectedFaculty.name}</h3>
                                <button className="btn" onClick={closeSubjectModal}><X size={20} /></button>
                            </div>

                            <div style={{ padding: '1.5rem', overflowY: 'auto', flex: 1 }}>
                                <p style={{ marginBottom: '1rem', color: 'var(--text-secondary)' }}>
                                    Select subjects and specific year-section combinations this faculty will teach.
                                </p>

                                {/* Filter Section */}
                                <div style={{ 
                                    marginBottom: '1.5rem', 
                                    padding: '1.25rem', 
                                    background: 'var(--background-color)', 
                                    borderRadius: '12px',
                                    border: '1px solid var(--border-color)',
                                    display: 'flex',
                                    flexDirection: 'column',
                                    gap: '1.25rem'
                                }}>
                                    {/* Department Filter */}
                                    <div>
                                        <label style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.5rem', display: 'block' }}>
                                            Filter Subjects by Department:
                                        </label>
                                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    setSelectedModalDept(null);
                                                    setSelectedYear(null);
                                                }}
                                                style={{
                                                    padding: '0.4rem 0.8rem',
                                                    borderRadius: '6px',
                                                    border: `1.5px solid ${selectedModalDept === null ? 'var(--primary-color)' : 'var(--border-color)'}`,
                                                    background: selectedModalDept === null ? 'var(--primary-color)' : 'white',
                                                    color: selectedModalDept === null ? 'white' : 'var(--text-primary)',
                                                    cursor: 'pointer',
                                                    fontSize: '0.8rem',
                                                    fontWeight: 600,
                                                    transition: 'all 0.2s'
                                                }}
                                            >
                                                All Departments
                                            </button>
                                            {availableDepartments.map(dept => (
                                                <button
                                                    key={dept.id}
                                                    type="button"
                                                    onClick={() => {
                                                        setSelectedModalDept(dept.id);
                                                        setSelectedYear(null);
                                                    }}
                                                    style={{
                                                        padding: '0.4rem 0.8rem',
                                                        borderRadius: '6px',
                                                        border: `1.5px solid ${selectedModalDept === dept.id ? 'var(--primary-color)' : 'var(--border-color)'}`,
                                                        background: selectedModalDept === dept.id ? 'var(--primary-color)' : 'white',
                                                        color: selectedModalDept === dept.id ? 'white' : 'var(--text-primary)',
                                                        cursor: 'pointer',
                                                        fontSize: '0.8rem',
                                                        fontWeight: 600,
                                                        transition: 'all 0.2s'
                                                    }}
                                                >
                                                    {dept.code}
                                                </button>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Year Filter */}
                                    <div>
                                        <label style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.5rem', display: 'block' }}>
                                            Filter Sections by Year:
                                        </label>
                                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                                            <button
                                                type="button"
                                                onClick={() => setSelectedYear(null)}
                                                style={{
                                                    padding: '0.4rem 0.8rem',
                                                    borderRadius: '6px',
                                                    border: `1.5px solid ${selectedYear === null ? 'var(--primary-color)' : 'var(--border-color)'}`,
                                                    background: selectedYear === null ? 'var(--primary-color)' : 'white',
                                                    color: selectedYear === null ? 'white' : 'var(--text-primary)',
                                                    cursor: 'pointer',
                                                    fontSize: '0.8rem',
                                                    fontWeight: 600,
                                                    transition: 'all 0.2s'
                                                }}
                                            >
                                                All Years
                                            </button>
                                            {(selectedModalDept
                                                ? availableYears.filter(year => year.department_id === selectedModalDept)
                                                : availableYears
                                            ).map(year => {
                                                const dept = availableDepartments.find(d => d.id === year.department_id);
                                                const label = dept ? `${dept.code} - ${year.name}` : year.name;
                                                return (
                                                    <button
                                                        key={year.id}
                                                        type="button"
                                                        onClick={() => setSelectedYear(year.id)}
                                                        style={{
                                                            padding: '0.4rem 0.8rem',
                                                            borderRadius: '6px',
                                                            border: `1.5px solid ${selectedYear === year.id ? 'var(--primary-color)' : 'var(--border-color)'}`,
                                                            background: selectedYear === year.id ? 'var(--primary-color)' : 'white',
                                                            color: selectedYear === year.id ? 'white' : 'var(--text-primary)',
                                                            cursor: 'pointer',
                                                            fontSize: '0.8rem',
                                                            fontWeight: 600,
                                                            transition: 'all 0.2s'
                                                        }}
                                                    >
                                                        {label}
                                                    </button>
                                                );
                                            })}
                                        </div>
                                    </div>

                                    {/* Subject Search */}
                                    <div>
                                        <label style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.5rem', display: 'block' }}>
                                            Search Subjects:
                                        </label>
                                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                                            <div style={{ position: 'relative', flex: 1 }}>
                                                <Search
                                                    size={16}
                                                    style={{
                                                        position: 'absolute',
                                                        left: '0.75rem',
                                                        top: '50%',
                                                        transform: 'translateY(-50%)',
                                                        color: 'var(--text-muted)'
                                                    }}
                                                />
                                                <input
                                                    type="text"
                                                    className="input-field"
                                                    placeholder="Search subjects by name or code..."
                                                    value={modalSearchQuery}
                                                    onChange={e => {
                                                        setModalSearchQuery(e.target.value);
                                                        if (e.target.value === '') {
                                                            setAppliedModalSearchQuery('');
                                                        }
                                                    }}
                                                    onKeyDown={e => {
                                                        if (e.key === 'Enter') {
                                                            setAppliedModalSearchQuery(modalSearchQuery);
                                                        }
                                                    }}
                                                    style={{
                                                        width: '100%',
                                                        paddingLeft: '2.5rem',
                                                        height: '2.5rem',
                                                        fontSize: '0.875rem',
                                                        margin: 0,
                                                        borderRadius: '8px'
                                                    }}
                                                />
                                                {modalSearchQuery && (
                                                    <button
                                                        type="button"
                                                        onClick={() => {
                                                            setModalSearchQuery('');
                                                            setAppliedModalSearchQuery('');
                                                        }}
                                                        style={{
                                                            position: 'absolute',
                                                            right: '0.75rem',
                                                            top: '50%',
                                                            transform: 'translateY(-50%)',
                                                            background: 'none',
                                                            border: 'none',
                                                            cursor: 'pointer',
                                                            color: 'var(--text-muted)',
                                                            display: 'flex',
                                                            alignItems: 'center',
                                                            justifyContent: 'center',
                                                            padding: 0
                                                        }}
                                                    >
                                                        <X size={14} />
                                                    </button>
                                                )}
                                            </div>
                                            <button
                                                type="button"
                                                className="btn btn-primary"
                                                onClick={() => setAppliedModalSearchQuery(modalSearchQuery)}
                                                style={{ height: '2.5rem', whiteSpace: 'nowrap', padding: '0 1.25rem', fontSize: '0.875rem' }}
                                            >
                                                <Search size={16} /> Search
                                            </button>
                                        </div>
                                    </div>
                                </div>

                                <div style={{ marginBottom: '1.5rem', padding: '1rem', background: 'white', border: '1px solid var(--border-color)', borderRadius: '8px' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
                                        <div>
                                            <div style={{ fontSize: '0.95rem', fontWeight: 700 }}>Availability Grid</div>
                                            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                                                Click a cell to cycle Available → Preferred → Unavailable.
                                            </div>
                                        </div>
                                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', fontSize: '0.75rem' }}>
                                            {Object.entries(availabilityStyles).map(([status, style]) => (
                                                <span key={status} style={{
                                                    padding: '0.25rem 0.5rem',
                                                    borderRadius: '999px',
                                                    background: style.background,
                                                    color: style.color,
                                                    border: `1px solid ${style.border}`,
                                                    fontWeight: 700
                                                }}>
                                                    {style.label}
                                                </span>
                                            ))}
                                        </div>
                                    </div>

                                    {availabilityLoading ? (
                                        <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Loading availability...</div>
                                    ) : availabilityRows.length === 0 ? (
                                        <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', fontStyle: 'italic' }}>
                                            No department time slots found for this faculty yet.
                                        </div>
                                    ) : (
                                        <div style={{ overflowX: 'auto' }}>
                                            <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: '0.35rem', minWidth: 620 }}>
                                                <thead>
                                                    <tr>
                                                        <th style={{ textAlign: 'left', fontSize: '0.75rem', color: 'var(--text-secondary)', width: 155 }}>Period</th>
                                                        {availabilityDays.map(day => (
                                                            <th key={day} style={{ textAlign: 'center', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{day.slice(0, 3)}</th>
                                                        ))}
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {availabilityRows.map(row => (
                                                        <tr key={`${row.start_time}-${row.end_time}`}>
                                                            <td style={{ fontSize: '0.76rem', fontWeight: 700, color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>
                                                                {formatTimeRange12Hour(row.start_time, row.end_time)}
                                                            </td>
                                                            {availabilityDays.map(day => {
                                                                const cellEntries = availabilityEntries.filter(entry =>
                                                                    entry.day === day &&
                                                                    entry.start_time === row.start_time &&
                                                                    entry.end_time === row.end_time
                                                                );
                                                                const status = availabilityCellStatus(cellEntries);
                                                                const style = availabilityStyles[status];
                                                                const cellKey = `${day}-${row.start_time}-${row.end_time}`;
                                                                const disabled = cellEntries.length === 0 || availabilitySavingKey === cellKey;
                                                                return (
                                                                    <td key={cellKey}>
                                                                        <button
                                                                            type="button"
                                                                            disabled={disabled}
                                                                            onClick={() => updateAvailabilityCell(cellEntries, cellKey)}
                                                                            title={cellEntries.length > 1 ? `${cellEntries.length} department slots` : style.label}
                                                                            style={{
                                                                                width: '100%',
                                                                                minHeight: 38,
                                                                                borderRadius: 8,
                                                                                border: `1.5px solid ${style.border}`,
                                                                                background: disabled && cellEntries.length === 0 ? '#f1f5f9' : style.background,
                                                                                color: style.color,
                                                                                cursor: disabled ? 'not-allowed' : 'pointer',
                                                                                fontSize: '0.72rem',
                                                                                fontWeight: 800,
                                                                                opacity: availabilitySavingKey === cellKey ? 0.65 : 1
                                                                            }}
                                                                        >
                                                                            {cellEntries.length === 0 ? '-' : style.label}
                                                                        </button>
                                                                    </td>
                                                                );
                                                            })}
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    )}
                                </div>

                                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                                    {filteredSubjectsInModal.length === 0 ? (
                                        <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-secondary)', background: '#f8fafc', borderRadius: '8px', border: '1px dashed var(--border-color)' }}>
                                            <Search size={32} style={{ margin: '0 auto 0.5rem', color: 'var(--text-muted)', display: 'block', opacity: 0.5 }} />
                                            <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>No Subjects Found</div>
                                            <div style={{ fontSize: '0.8rem', marginTop: '0.25rem' }}>Try clearing your filters or search query.</div>
                                        </div>
                                    ) : (
                                        filteredSubjectsInModal.map(sub => {
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
                                        })
                                    )}
                                </div>
                            </div>

                            <div style={{ padding: '1.5rem', borderTop: '1px solid var(--border-color)', display: 'flex', justifyContent: 'flex-end', gap: '1rem' }}>
                                <button className="btn" onClick={closeSubjectModal}>Cancel</button>
                                <button className="btn btn-primary" onClick={saveSubjectAssignments}>
                                    Save Assignments ({subjectAssignments.length})
                                </button>
                            </div>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>

            {filteredFaculty.length === 0 ? (
                <div className="card" style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-secondary)' }}>
                    <Search size={48} style={{ margin: '0 auto 1rem', color: 'var(--text-muted)', display: 'block', opacity: 0.5 }} />
                    <h3 style={{ margin: '0 0 0.5rem' }}>No Faculty Found</h3>
                    <p style={{ margin: 0 }}>We couldn't find any faculty members matching "{appliedSearchQuery}".</p>
                    <button
                        className="btn btn-outline"
                        onClick={() => {
                            setSearchQuery('');
                            setAppliedSearchQuery('');
                        }}
                        style={{ marginTop: '1rem' }}
                    >
                        Clear Search
                    </button>
                </div>
            ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1.5rem' }}>
                    {filteredFaculty.map(fac => (
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
                                        {fac.departments && fac.departments.length > 0 && (
                                            <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
                                                {fac.departments.map(dept => (
                                                    <span key={dept.id} style={{ fontSize: '0.72rem', background: '#eef2ff', color: '#3730a3', padding: '2px 8px', borderRadius: '999px', fontWeight: 600 }}>
                                                        {dept.code}
                                                    </span>
                                                ))}
                                            </div>
                                        )}
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
            )}
        </div>
    );
};

export default FacultyManager;
