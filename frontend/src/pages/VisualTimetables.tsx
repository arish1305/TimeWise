import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { DndContext, PointerSensor, closestCenter, useDraggable, useDroppable, useSensor, useSensors } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import { 
    AlertTriangle, 
    CheckCircle2, 
    Clock3, 
    Download, 
    History, 
    Lock, 
    RefreshCw, 
    Save, 
    Search, 
    Trash2, 
    Undo, 
    Redo, 
    Sparkles, 
    Filter, 
    Calendar, 
    Users, 
    Layers, 
    FileText, 
    AlertCircle, 
    Info 
} from 'lucide-react';
import api from '../api/axios';
import '../styles/VisualTimetables.css';
import { downloadAllTimetablesPdf } from '../utils/pdfExport';
import { downloadAllTimetablesWord } from '../utils/wordExport';

type Slot = {
    id: number;
    day: string;
    start_time: string;
    end_time: string;
    is_break: boolean;
    label?: string;
};

type Entry = {
    id: number;
    timetable_id: number;
    subject_id: number;
    faculty_id?: number | null;
    timeslot_id: number;
    room_id?: number | null;
    is_locked: boolean;
    is_manual?: boolean;
    subject?: any;
    faculty?: any;
    section?: any;
    section_name?: string;
    start_time?: string;
    end_time?: string;
    timeslot?: any;
};

type Timetable = {
    id: number;
    section_id: number;
    semester: number;
    version: number;
    status: string;
    section: any;
    entries: Entry[];
};

type EditOperation = {
    entry_id: number;
    source_slot: number;
    target_slot: number;
    target_room?: number | null;
    action: 'move' | 'swap' | 'duplicate' | 'lock' | 'delete';
};

type BoardState = {
    timetables: Timetable[];
    time_slots: Slot[];
};

const DraggableEntryCard = ({ 
    entry, 
    searchQuery, 
    onLock, 
    onDelete,
    isEditingMode = false
}: { 
    entry: Entry; 
    searchQuery: string; 
    onLock?: (entry: Entry) => void; 
    onDelete?: (entry: Entry) => void; 
    isEditingMode?: boolean;
}) => {
    const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
        id: `entry-${entry.id}`,
        disabled: !isEditingMode || entry.is_locked,
        data: { entryId: entry.id }
    });

    const style = {
        transform: CSS.Translate.toString(transform),
        opacity: isDragging ? 0.4 : 1
    };

    const cardType = entry.is_locked ? 'locked' : (entry.is_manual ? 'manual' : (entry.subject?.subject_type === 'LAB' ? 'lab' : 'theory'));
    
    const isMatched = useMemo(() => {
        if (!searchQuery) return false;
        const q = searchQuery.toLowerCase();
        const code = (entry.subject?.code || '').toLowerCase();
        const name = (entry.subject?.name || '').toLowerCase();
        const fac = (entry.faculty?.name || '').toLowerCase();
        const room = String(entry.room_id || '').toLowerCase();
        const sec = (entry.section?.name || entry.section_name || '').toLowerCase();
        return code.includes(q) || name.includes(q) || fac.includes(q) || room.includes(q) || sec.includes(q);
    }, [searchQuery, entry]);

    const isDimmed = searchQuery && !isMatched;

    const duration = useMemo(() => {
        const start = entry.start_time || entry.timeslot?.start_time;
        const end = entry.end_time || entry.timeslot?.end_time;
        if (!start || !end) return '1h';
        try {
            const [sh, sm] = start.split(':').map(Number);
            const [eh, em] = end.split(':').map(Number);
            const diffMins = (eh * 60 + em) - (sh * 60 + sm);
            const hrs = diffMins / 60;
            if (diffMins % 60 === 0) return `${hrs}h`;
            return `${hrs.toFixed(1)}h`;
        } catch {
            return '1h';
        }
    }, [entry]);

    return (
        <div 
            ref={setNodeRef} 
            style={style} 
            className={`board-entry type-${cardType} ${isMatched ? 'search-matched' : ''} ${isDimmed ? 'search-dimmed' : ''}`}
            {...listeners} 
            {...attributes}
        >
            <div className="board-entry-header">
                <span className="entry-subject-code">{entry.subject?.code || 'SUB'}</span>
                <span className="entry-duration">{duration}</span>
            </div>
            <div className="entry-subject-name" title={entry.subject?.name}>{entry.subject?.name || 'Subject Name'}</div>
            <div className="entry-faculty-name">{entry.faculty?.name || 'Unassigned'}</div>
            
            <div className="board-entry-footer">
                <span className="entry-room">{entry.room_id ? `Room ${entry.room_id}` : 'Unassigned'}</span>
                <span className="entry-section">{entry.section?.name || entry.section_name || ''}</span>
            </div>
            
            {isEditingMode && (
                <div className="entry-actions" onClick={e => e.stopPropagation()} onPointerDown={e => e.stopPropagation()}>
                    {!entry.is_locked && onLock && (
                        <button className="action-btn lock-btn" title="Lock Card" onClick={() => onLock(entry)}>
                            <Lock size={11} />
                        </button>
                    )}
                    {onDelete && (
                        <button className="action-btn delete-btn" title="Delete Card" onClick={() => onDelete(entry)}>
                            <Trash2 size={11} />
                        </button>
                    )}
                </div>
            )}
        </div>
    );
};

const DroppableCell = ({
    id,
    children,
    isConflict,
    isWarning,
    isTarget,
    isDimmed,
    onClick
}: {
    id: string;
    children: React.ReactNode;
    isConflict?: boolean;
    isWarning?: boolean;
    isTarget?: boolean;
    isDimmed?: boolean;
    onClick?: () => void;
}) => {
    const { setNodeRef, isOver } = useDroppable({ id, disabled: isDimmed });
    
    let cellClass = 'board-cell';
    if (isOver) cellClass += ' drop-over';
    if (isConflict) cellClass += ' cell-conflict';
    if (isWarning) cellClass += ' cell-warning';
    if (isTarget) cellClass += ' cell-target';
    if (isDimmed) cellClass += ' cell-dimmed';
    
    return (
        <td ref={setNodeRef} className={cellClass} onClick={onClick}>
            {children}
        </td>
    );
};

const DroppableLane = ({
    id,
    children,
    isConflict,
    isWarning,
    isTarget,
    isDimmed,
    sectionName
}: {
    id: string;
    children: React.ReactNode;
    isConflict?: boolean;
    isWarning?: boolean;
    isTarget?: boolean;
    isDimmed?: boolean;
    sectionName: string;
}) => {
    const { setNodeRef, isOver } = useDroppable({ id, disabled: isDimmed });
    
    let laneClass = 'compare-lane';
    if (isOver) laneClass += ' drop-over';
    if (isConflict) laneClass += ' cell-conflict';
    if (isWarning) laneClass += ' cell-warning';
    if (isTarget) laneClass += ' cell-target';
    if (isDimmed) laneClass += ' cell-dimmed';
    
    return (
        <div ref={setNodeRef} className={laneClass}>
            <div className="lane-header">{sectionName}</div>
            <div className="lane-content">
                {children}
            </div>
        </div>
    );
};

const VisualTimetables = () => {
    const [allTimetablesList, setAllTimetablesList] = useState<any[]>([]);
    const [initialLoading, setInitialLoading] = useState(true);

    const [departments, setDepartments] = useState<any[]>([]);
    const [years, setYears] = useState<any[]>([]);
    const [faculties, setFaculties] = useState<any[]>([]);
    
    const [selectedDept, setSelectedDept] = useState<string>('');
    const [selectedYear, setSelectedYear] = useState<string>('');
    const [selectedSemester, setSelectedSemester] = useState<number>(1);

    const [board, setBoard] = useState<BoardState>({ timetables: [], time_slots: [] });
    const [loadingBoard, setLoadingBoard] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [lastValidation, setLastValidation] = useState<any>(null);
    const [suggestions, setSuggestions] = useState<any[]>([]);
    const [pendingOps, setPendingOps] = useState<EditOperation[]>([]);
    const [selectedTimetableId, setSelectedTimetableId] = useState<number | null>(null);
    const [selectedCompareTimetableIds, setSelectedCompareTimetableIds] = useState<number[]>([]);
    const [selectedFacultyId, setSelectedFacultyId] = useState<number | null>(null);
    const [facultyTimetable, setFacultyTimetable] = useState<any | null>(null);
    const [loadingFaculty, setLoadingFaculty] = useState(false);
    
    const [searchQuery, setSearchQuery] = useState<string>('');
    const [viewMode, setViewMode] = useState<'tabs' | 'compare' | 'faculty'>('tabs');
    const [activeDragEntry, setActiveDragEntry] = useState<Entry | null>(null);
    
    const [historyEvents, setHistoryEvents] = useState<any[]>([]);
    const [undoStack, setUndoStack] = useState<BoardState[]>([]);
    const [redoStack, setRedoStack] = useState<BoardState[]>([]);

    const [sidebarSearch, setSidebarSearch] = useState<string>('');
    const [exportOpen, setExportOpen] = useState(false);
    const [isEditingMode, setIsEditingMode] = useState<boolean>(false);

    const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

    const fetchTimetablesList = async () => {
        try {
            const res = await api.get('/timetables/');
            setAllTimetablesList(res.data || []);
        } catch (err) {
            console.error("Failed to fetch timetables list", err);
        }
    };

    // Fetch initial data
    useEffect(() => {
        const loadInitial = async () => {
            try {
                setInitialLoading(true);
                const [dRes, fRes, tRes] = await Promise.all([
                    api.get('/admin/departments'),
                    api.get('/admin/faculty'),
                    api.get('/timetables/')
                ]);
                setDepartments(dRes.data || []);
                setFaculties(fRes.data || []);
                
                const timetables = tRes.data || [];
                setAllTimetablesList(timetables);
                
                if (timetables.length > 0) {
                    const firstTT = timetables[0];
                    const deptId = firstTT.section?.academic_year?.department_id || firstTT.department_id;
                    const yearId = firstTT.section?.academic_year_id;
                    const sem = firstTT.semester;
                    
                    if (deptId) setSelectedDept(String(deptId));
                    if (yearId) setSelectedYear(String(yearId));
                    if (sem) setSelectedSemester(sem);
                    setSelectedTimetableId(firstTT.id);
                }
            } catch (err) {
                setError('Failed to initialize workspace data');
            } finally {
                setInitialLoading(false);
            }
        };
        loadInitial();
    }, []);

    // Load Academic Years when department changes
    useEffect(() => {
        if (!selectedDept) {
            setYears([]);
            setSelectedYear('');
            return;
        }
        api.get('/admin/academic-years', { params: { department_id: selectedDept } })
            .then(res => setYears(res.data || []))
            .catch(() => setError('Failed to load academic years'));
    }, [selectedDept]);

    // Auto-load timetable board on selector change
    const loadBoard = async () => {
        if (!selectedDept) return;
        setLoadingBoard(true);
        setError(null);
        try {
            const res = await api.get('/timetables/board', {
                params: {
                    department_id: Number(selectedDept),
                    semester: Number(selectedSemester),
                    academic_year_id: selectedYear ? Number(selectedYear) : undefined
                }
            });
            const timetables: Timetable[] = (res.data?.timetables || []).map((tt: any) => ({
                ...tt,
                entries: (tt.entries || []).map((e: any) => ({ ...e, timetable_id: tt.id, section: tt.section }))
            }));
            
            setBoard({
                timetables,
                time_slots: res.data?.time_slots || []
            });
            setPendingOps([]);
            setUndoStack([]);
            setRedoStack([]);
            
            // Auto-select first timetable if none is selected
            if (timetables.length > 0) {
                setSelectedTimetableId(timetables[0].id);
                // Pre-select all section IDs for Compare Mode
                setSelectedCompareTimetableIds(timetables.map(t => t.id));
            } else {
                setSelectedTimetableId(null);
                setSelectedCompareTimetableIds([]);
            }
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to load visual board');
        } finally {
            setLoadingBoard(false);
        }
    };

    useEffect(() => {
        if (selectedDept) {
            loadBoard();
        } else {
            setBoard({ timetables: [], time_slots: [] });
            setSelectedTimetableId(null);
            setSelectedCompareTimetableIds([]);
        }
    }, [selectedDept, selectedYear, selectedSemester]);

    // Load Faculty Timetable when faculty is selected
    const loadFacultyTimetable = async (facultyId: number) => {
        setLoadingFaculty(true);
        try {
            const res = await api.get('/timetables/faculty', { params: { faculty_id: facultyId } });
            const facultyData = res.data;
            if (facultyData && facultyData.entries) {
                // Map the entries to stable IDs by finding matches in our board
                const mappedEntries = facultyData.entries.map((fe: any) => {
                    const timetable = board.timetables.find(t => t.id === fe.timetable_id);
                    const realEntry = timetable?.entries.find(e => e.subject_id === fe.subject_id && e.timeslot_id === fe.timeslot_id);
                    return {
                        ...fe,
                        id: realEntry ? realEntry.id : `fac-ext-${fe.timetable_id}-${fe.subject_id}-${fe.timeslot_id}`
                    };
                });
                setFacultyTimetable({
                    ...facultyData,
                    entries: mappedEntries
                });
            } else {
                setFacultyTimetable(null);
            }
        } catch (err: any) {
            setError('Failed to load faculty timetable');
        } finally {
            setLoadingFaculty(false);
        }
    };

    useEffect(() => {
        if (viewMode === 'faculty' && selectedFacultyId) {
            loadFacultyTimetable(selectedFacultyId);
        } else {
            setFacultyTimetable(null);
        }
    }, [selectedFacultyId, viewMode, board.timetables]);

    // Fetch history logs for selected timetable
    useEffect(() => {
        if (!selectedTimetableId) {
            setHistoryEvents([]);
            return;
        }
        api.get(`/timetables/${selectedTimetableId}/history`)
            .then(res => setHistoryEvents(res.data || []))
            .catch(() => setHistoryEvents([]));
    }, [selectedTimetableId, pendingOps.length]);

    // generateDepartmentSchedule removed

    // Helper to calculate timeslot duration
    const timeRows = useMemo(() => {
        const byKey = new Map<string, { start_time: string; end_time: string; is_break: boolean; label?: string }>();
        board.time_slots.forEach(slot => {
            const key = `${slot.start_time}-${slot.end_time}`;
            if (!byKey.has(key)) {
                byKey.set(key, {
                    start_time: slot.start_time,
                    end_time: slot.end_time,
                    is_break: slot.is_break,
                    label: slot.label
                });
            } else if (slot.is_break) {
                byKey.get(key)!.is_break = true;
                if (slot.label) {
                    byKey.get(key)!.label = slot.label;
                }
            }
        });
        return Array.from(byKey.values()).sort((a, b) => a.start_time.localeCompare(b.start_time));
    }, [board.time_slots]);

    const dayColumns = useMemo(() => ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'], []);

    const handleSelectTimetable = (tt: any) => {
        const deptId = tt.section?.academic_year?.department_id || tt.department_id;
        const yearId = tt.section?.academic_year_id;
        const sem = tt.semester;
        
        setSelectedDept(deptId ? String(deptId) : '');
        setSelectedYear(yearId ? String(yearId) : '');
        setSelectedSemester(sem || 1);
        setSelectedTimetableId(tt.id);
    };

    const filteredGroupedTimetables = useMemo(() => {
        if (!sidebarSearch) return allTimetablesList;
        const q = sidebarSearch.toLowerCase();
        return allTimetablesList.filter(tt => {
            const secName = (tt.section?.name || '').toLowerCase();
            const deptCode = (tt.section?.academic_year?.department?.code || tt.department_code || '').toLowerCase();
            const deptName = (tt.section?.academic_year?.department?.name || tt.department_name || '').toLowerCase();
            const yearName = (tt.section?.academic_year?.name || '').toLowerCase();
            return secName.includes(q) || deptCode.includes(q) || deptName.includes(q) || yearName.includes(q);
        });
    }, [allTimetablesList, sidebarSearch]);

    const groupedFilteredTimetables = useMemo(() => {
        const groups: Record<string, {
            departmentName: string;
            departmentCode: string;
            years: Record<string, {
                yearName: string;
                semesters: Record<number, any[]>;
            }>;
        }> = {};

        filteredGroupedTimetables.forEach(tt => {
            const dept = tt.section?.academic_year?.department || { id: 0, name: 'General', code: 'GEN' };
            const deptKey = `${dept.id}`;
            const yearId = tt.section?.academic_year_id || 0;
            const yearName = tt.section?.academic_year?.name || 'General';
            const sem = tt.semester;

            if (!groups[deptKey]) {
                groups[deptKey] = {
                    departmentName: dept.name,
                    departmentCode: dept.code,
                    years: {}
                };
            }

            if (!groups[deptKey].years[yearId]) {
                groups[deptKey].years[yearId] = {
                    yearName: yearName,
                    semesters: {}
                };
            }

            if (!groups[deptKey].years[yearId].semesters[sem]) {
                groups[deptKey].years[yearId].semesters[sem] = [];
            }

            groups[deptKey].years[yearId].semesters[sem].push(tt);
        });

        return groups;
    }, [filteredGroupedTimetables]);

    // Filter lists
    const filteredSections = useMemo(() => {
        if (!board.timetables) return [];
        return board.timetables.filter(t => 
            t.section?.name?.toLowerCase().includes(sidebarSearch.toLowerCase())
        );
    }, [board.timetables, sidebarSearch]);

    const filteredFaculties = useMemo(() => {
        if (!faculties) return [];
        return faculties.filter(f => 
            f.name?.toLowerCase().includes(sidebarSearch.toLowerCase()) ||
            f.faculty_id_code?.toLowerCase().includes(sidebarSearch.toLowerCase())
        );
    }, [faculties, sidebarSearch]);

    // Active status based on selected timetable
    const currentTimetableStatus = useMemo(() => {
        if (viewMode === 'tabs' && selectedTimetableId) {
            return board.timetables.find(t => t.id === selectedTimetableId)?.status || 'DRAFT';
        }
        if (viewMode === 'compare' && selectedCompareTimetableIds.length > 0) {
            const statuses = selectedCompareTimetableIds.map(id => board.timetables.find(t => t.id === id)?.status || 'DRAFT');
            return statuses.every(s => s === statuses[0]) ? statuses[0] : 'MIXED';
        }
        return 'DRAFT';
    }, [viewMode, selectedTimetableId, selectedCompareTimetableIds, board.timetables]);

    // Undo / Redo mechanics
    const pushUndoSnapshot = () => {
        setUndoStack(prev => {
            const snapshot: BoardState = {
                timetables: JSON.parse(JSON.stringify(board.timetables)),
                time_slots: board.time_slots
            };
            const merged = [...prev, snapshot];
            return merged.length > 50 ? merged.slice(merged.length - 50) : merged;
        });
        setRedoStack([]);
    };

    const applyLocalOperation = (operation: EditOperation) => {
        pushUndoSnapshot();
        setBoard(prev => {
            const next: BoardState = {
                time_slots: prev.time_slots,
                timetables: prev.timetables.map(tt => ({
                    ...tt,
                    entries: tt.entries.map(e => ({ ...e }))
                }))
            };
            const tt = next.timetables.find(t => t.entries.some(e => e.id === operation.entry_id));
            if (!tt) return prev;

            const moving = tt.entries.find(e => e.id === operation.entry_id);
            if (!moving) return prev;

            if (operation.action === 'swap') {
                const target = tt.entries.find(e => e.timeslot_id === operation.target_slot && e.id !== moving.id);
                if (target) {
                    const src = moving.timeslot_id;
                    moving.timeslot_id = operation.target_slot;
                    target.timeslot_id = src;
                }
            } else if (operation.action === 'duplicate') {
                const duplicate: Entry = {
                    ...moving,
                    id: -Math.floor(Math.random() * 1000000000),
                    timeslot_id: operation.target_slot,
                    is_locked: false
                };
                tt.entries.push(duplicate);
            } else if (operation.action === 'lock') {
                moving.is_locked = true;
            } else if (operation.action === 'delete') {
                tt.entries = tt.entries.filter(e => e.id !== moving.id);
            } else {
                moving.timeslot_id = operation.target_slot;
            }
            return next;
        });
        setPendingOps(prev => [...prev, operation]);
    };

    // Drag-Drop handlers
    const handleDragStart = (event: any) => {
        const activeId = String(event.active?.id || '');
        if (activeId.startsWith('entry-')) {
            const entryId = Number(activeId.replace('entry-', ''));
            
            // Find the entry in our active board timetables
            let foundEntry = null;
            for (const tt of board.timetables) {
                const e = tt.entries.find(x => x.id === entryId);
                if (e) {
                    foundEntry = e;
                    break;
                }
            }
            // If not found in board, search in faculty entries
            if (!foundEntry && facultyTimetable?.entries) {
                const fe = facultyTimetable.entries.find((x: any) => x.id === entryId);
                if (fe) {
                    const timetable = board.timetables.find(t => t.id === fe.timetable_id);
                    foundEntry = timetable?.entries.find(e => e.id === fe.id);
                }
            }
            
            if (foundEntry) {
                setActiveDragEntry(foundEntry);
            }
        }
    };

    const handleDragEnd = async (event: any) => {
        setActiveDragEntry(null);
        const activeId = String(event.active?.id || '');
        const overId = String(event.over?.id || '');
        if (!activeId.startsWith('entry-') || !overId.startsWith('slot-')) return;

        const entryId = Number(activeId.replace('entry-', ''));
        const [, ttIdRaw, slotRaw] = overId.split('-');
        const targetSlot = Number(slotRaw);
        const targetTimetableId = Number(ttIdRaw);

        // Find parent timetable
        const timetable = board.timetables.find(tt => tt.id === targetTimetableId);
        if (!timetable) return;

        const entry = timetable.entries.find(e => e.id === entryId) || 
                      board.timetables.flatMap(tt => tt.entries).find(e => e.id === entryId);
        if (!entry) return;

        // Restriction check
        if (entry.timetable_id !== targetTimetableId) {
            setError('Cross-section drag is restricted by backend constraint.');
            return;
        }

        if (entry.timeslot_id === targetSlot) return;

        const targetExists = timetable.entries.find(e => e.timeslot_id === targetSlot && e.id !== entryId);
        const action: EditOperation['action'] = targetExists ? 'swap' : 'move';
        const operation: EditOperation = {
            entry_id: entryId,
            source_slot: entry.timeslot_id,
            target_slot: targetSlot,
            action
        };

        try {
            const res = await api.put('/timetables/edit', { ...operation, apply: false });
            setLastValidation(res.data?.validation || null);
            setSuggestions(res.data?.suggestions || []);
            
            if (res.data?.status === 'VALID' || res.data?.status === 'APPLIED') {
                applyLocalOperation(operation);
                setError(null);
            } else {
                setError(res.data?.message || 'Move rejected by constraint validation.');
            }
        } catch (err: any) {
            const detail = err.response?.data?.detail;
            if (detail && typeof detail === 'object') {
                setError(detail.message || 'Invalid move rejected');
                setSuggestions(detail.suggestions || []);
            } else {
                setError(err.response?.data?.detail || 'Move validation failed');
            }
        }
    };

    // Save pending operations to server
    const saveAllChanges = async () => {
        if (pendingOps.length === 0) return;
        setSaving(true);
        setError(null);
        try {
            for (const operation of pendingOps) {
                await api.put('/timetables/edit', { ...operation, apply: true });
            }
            setPendingOps([]);
            await loadBoard();
            await fetchTimetablesList();
            if (viewMode === 'faculty' && selectedFacultyId) {
                await loadFacultyTimetable(selectedFacultyId);
            }
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to save timetable changes.');
        } finally {
            setSaving(false);
        }
    };

    // Approve timetable and reload
    const handleApprove = async () => {
        if (!selectedTimetableId) return;
        setSaving(true);
        setError(null);
        try {
            await api.post(`/timetables/${selectedTimetableId}/approve`);
            await loadBoard();
            await fetchTimetablesList();
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to approve timetable');
        } finally {
            setSaving(false);
        }
    };

    // Card Actions: Lock and Delete
    const handleLockCard = async (entry: Entry) => {
        const operation: EditOperation = {
            entry_id: entry.id,
            source_slot: entry.timeslot_id,
            target_slot: entry.timeslot_id,
            action: 'lock'
        };
        try {
            const res = await api.put('/timetables/edit', { ...operation, apply: false });
            if (res.data?.status === 'VALID' || res.data?.status === 'APPLIED') {
                applyLocalOperation(operation);
                setError(null);
            } else {
                setError(res.data?.message || 'Failed to lock card');
            }
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Lock failed');
        }
    };

    const handleDeleteCard = async (entry: Entry) => {
        const operation: EditOperation = {
            entry_id: entry.id,
            source_slot: entry.timeslot_id,
            target_slot: entry.timeslot_id,
            action: 'delete'
        };
        try {
            const res = await api.put('/timetables/edit', { ...operation, apply: false });
            if (res.data?.status === 'VALID' || res.data?.status === 'APPLIED') {
                applyLocalOperation(operation);
                setError(null);
            } else {
                setError(res.data?.message || 'Failed to delete card');
            }
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Delete failed');
        }
    };

    // Undo / Redo buttons
    const handleUndo = () => {
        if (undoStack.length === 0) return;
        setRedoStack(prev => [...prev, { timetables: JSON.parse(JSON.stringify(board.timetables)), time_slots: board.time_slots }]);
        const previous = undoStack[undoStack.length - 1];
        setUndoStack(prev => prev.slice(0, prev.length - 1));
        setBoard(previous);
        setPendingOps(prev => prev.slice(0, Math.max(0, prev.length - 1)));
    };

    const handleRedo = () => {
        if (redoStack.length === 0) return;
        setUndoStack(prev => [...prev, { timetables: JSON.parse(JSON.stringify(board.timetables)), time_slots: board.time_slots }]);
        const next = redoStack[redoStack.length - 1];
        setRedoStack(prev => prev.slice(0, prev.length - 1));
        setBoard(next);
        // Note: Redo doesn't re-apply operations on server, they are still committed during save.
    };

    // Export PDF / Word
    const exportBoardPdf = async () => {
        setExportOpen(false);
        const details = await Promise.all(board.timetables.map(tt => api.get(`/timetables/${tt.id}`)));
        await downloadAllTimetablesPdf(details.map(r => r.data), board.time_slots);
    };

    const exportBoardWord = async () => {
        setExportOpen(false);
        const details = await Promise.all(board.timetables.map(tt => api.get(`/timetables/${tt.id}`)));
        downloadAllTimetablesWord(details.map(r => r.data), board.time_slots);
    };

    // Dynamically resolve faculty entries mapping
    const resolvedFacultyEntries = useMemo(() => {
        if (!facultyTimetable?.entries) return [];
        return facultyTimetable.entries.map((fe: any) => {
            const localEntry = board.timetables
                .flatMap(t => t.entries)
                .find(e => e.id === fe.id);
            if (localEntry) {
                return { ...fe, current_timeslot_id: localEntry.timeslot_id, is_locked: localEntry.is_locked, is_manual: localEntry.is_manual };
            }
            return { ...fe, current_timeslot_id: fe.timeslot_id };
        });
    }, [facultyTimetable, board.timetables]);

    // Active Section Details in Workspace
    const activeSectionTimetable = useMemo(() => {
        return board.timetables.find(t => t.id === selectedTimetableId) || null;
    }, [selectedTimetableId, board.timetables]);

    if (initialLoading) {
        return (
            <div className="workspace-container">
                <div className="empty-workspace" style={{ height: '80vh' }}>
                    <RefreshCw className="empty-icon animate-spin" size={48} />
                    <h2>Loading Timetable Boards...</h2>
                    <p>Fetching generated schedules and workspace dependencies.</p>
                </div>
            </div>
        );
    }

    if (allTimetablesList.length === 0) {
        return (
            <div className="workspace-container">
                <div className="empty-workspace" style={{ height: '80vh', gap: '1rem' }}>
                    <AlertCircle className="empty-icon" size={64} style={{ color: 'var(--primary-500)' }} />
                    <h2 style={{ fontSize: '1.75rem', fontWeight: 800 }}>No Timetables Generated Yet</h2>
                    <p style={{ maxWidth: '480px', fontSize: '0.95rem', color: 'var(--neutral-600)', lineHeight: 1.6 }}>
                        Before you can edit and visualize schedules in the Visual Board, you need to generate them using the standard AI Timetable Generator.
                    </p>
                    <Link to="/admin/timetables" className="toolbar-btn btn-primary" style={{ padding: '0.6rem 1.5rem', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Sparkles size={16} />
                        <span>Go to Timetable Generator</span>
                    </Link>
                </div>
            </div>
        );
    }

    return (
        <div className={`workspace-container ${isEditingMode ? 'editing-mode' : ''}`}>
            {/* Top Toolbar */}
            <header className="workspace-toolbar">
                <div className="toolbar-left">
                    <div className="workspace-title-row">
                        <Calendar className="title-icon" size={20} />
                        <h1>{isEditingMode ? 'Visual Scheduler Editor' : 'Interactive Workspace'}</h1>
                        <span className={`status-badge ${currentTimetableStatus.toLowerCase()}`}>
                            {currentTimetableStatus}
                        </span>
                    </div>
                    <p className="subtitle">
                        {isEditingMode 
                            ? `Editing: Section ${activeSectionTimetable?.section?.name || ''} • Sem ${selectedSemester}`
                            : (board.timetables.length > 0 
                                ? `${board.timetables.length} Timetables Loaded • Semester ${selectedSemester}` 
                                : 'No timetables loaded. Please select department.')}
                    </p>
                </div>

                <div className="toolbar-center">
                    {!isEditingMode && (
                        <div className="selector-group">
                            <div className="selector-wrapper">
                                <Layers size={13} className="select-icon" />
                                <select 
                                    value={selectedDept} 
                                    onChange={e => setSelectedDept(e.target.value)}
                                    className="styled-select"
                                >
                                    <option value="">Select Dept</option>
                                    {departments.map(d => <option key={d.id} value={d.id}>{d.code}</option>)}
                                </select>
                            </div>

                            <div className="selector-wrapper">
                                <Calendar size={13} className="select-icon" />
                                <select 
                                    value={selectedYear} 
                                    onChange={e => setSelectedYear(e.target.value)}
                                    disabled={!selectedDept}
                                    className="styled-select"
                                >
                                    <option value="">All Years</option>
                                    {years.map(y => <option key={y.id} value={y.id}>{y.name}</option>)}
                                </select>
                            </div>

                            <div className="selector-wrapper">
                                <Clock3 size={13} className="select-icon" />
                                <select
                                    value={selectedSemester}
                                    onChange={e => setSelectedSemester(Number(e.target.value))}
                                    className="styled-select"
                                >
                                    {[1,2,3,4,5,6,7,8].map(s => (
                                        <option key={s} value={s}>Sem {s}</option>
                                    ))}
                                </select>
                            </div>
                        </div>
                    )}
                </div>

                <div className="toolbar-right">
                    {isEditingMode ? (
                        <>
                            <div className="history-controls">
                                <button 
                                    className="toolbar-btn btn-square" 
                                    onClick={handleUndo} 
                                    disabled={undoStack.length === 0}
                                    title="Undo (Ctrl+Z)"
                                >
                                    <Undo size={15} />
                                </button>
                                <button 
                                    className="toolbar-btn btn-square" 
                                    onClick={handleRedo} 
                                    disabled={redoStack.length === 0}
                                    title="Redo (Ctrl+Y)"
                                >
                                    <Redo size={15} />
                                </button>
                            </div>

                            <button 
                                className="toolbar-btn btn-primary" 
                                onClick={saveAllChanges} 
                                disabled={saving || pendingOps.length === 0}
                            >
                                {saving ? (
                                    <RefreshCw className="animate-spin" size={15} />
                                ) : (
                                    <Save size={15} />
                                )}
                                <span>Save Edited Timetable {pendingOps.length > 0 && `(${pendingOps.length})`}</span>
                            </button>

                            <button 
                                className="toolbar-btn btn-secondary" 
                                onClick={() => {
                                    setPendingOps([]);
                                    setUndoStack([]);
                                    setRedoStack([]);
                                    setIsEditingMode(false);
                                    loadBoard();
                                }}
                            >
                                <span>Close Editor</span>
                            </button>
                        </>
                    ) : (
                        <>
                            <div className="export-menu-container">
                                <button 
                                    className="toolbar-btn btn-secondary" 
                                    disabled={!board.timetables.length}
                                    onClick={() => setExportOpen(!exportOpen)}
                                >
                                    <Download size={15} />
                                    <span>Export</span>
                                </button>
                                {exportOpen && (
                                    <div className="export-dropdown">
                                        <button onClick={exportBoardPdf}>
                                            <FileText size={14} /> Export to PDF
                                        </button>
                                        <button onClick={exportBoardWord}>
                                            <FileText size={14} /> Export to Word
                                        </button>
                                    </div>
                                )}
                            </div>
                        </>
                    )}
                </div>
            </header>

            {/* Layout Workspace Grid */}
            <div className="workspace-layout">
                {/* Left Panel */}
                {!isEditingMode && (
                    <aside className="left-panel">
                    <div className="panel-section">
                        <h3 className="section-title">View Mode</h3>
                        <div className="segmented-switch">
                            <button 
                                className={viewMode === 'tabs' ? 'active' : ''} 
                                onClick={() => { setViewMode('tabs'); setSidebarSearch(''); }}
                            >
                                <Layers size={14} />
                                <span>Section Tabs</span>
                            </button>
                            <button 
                                className={viewMode === 'compare' ? 'active' : ''} 
                                onClick={() => { setViewMode('compare'); setSidebarSearch(''); }}
                            >
                                <Users size={14} />
                                <span>Compare</span>
                            </button>
                            <button 
                                className={viewMode === 'faculty' ? 'active' : ''} 
                                onClick={() => { setViewMode('faculty'); setSidebarSearch(''); }}
                            >
                                <Users size={14} />
                                <span>Faculty</span>
                            </button>
                        </div>
                    </div>

                    <div className="panel-section flex-grow">
                        <div className="panel-search-box">
                            <Search className="search-icon" size={14} />
                            <input 
                                placeholder={viewMode === 'faculty' ? "Search faculty..." : "Search timetables..."}
                                value={sidebarSearch}
                                onChange={e => setSidebarSearch(e.target.value)}
                                className="search-input"
                            />
                        </div>

                        <div className="list-scrollbar-container">
                        {viewMode === 'tabs' && (
                            <div className="tree-sidebar-container">
                                {Object.keys(groupedFilteredTimetables).map(deptId => {
                                    const deptGroup = groupedFilteredTimetables[deptId];
                                    return (
                                        <div key={deptId} className="dept-sidebar-group">
                                            <div className="dept-sidebar-header">
                                                <span className="dept-code-badge">{deptGroup.departmentCode}</span>
                                                <span className="dept-name" title={deptGroup.departmentName}>{deptGroup.departmentName}</span>
                                            </div>
                                            <div className="dept-sidebar-content">
                                                {Object.keys(deptGroup.years).map(yearId => {
                                                    const yearGroup = deptGroup.years[yearId];
                                                    return (
                                                        <div key={yearId} className="year-sidebar-group">
                                                            <div className="year-sidebar-title">{yearGroup.yearName}</div>
                                                            {Object.keys(yearGroup.semesters).map(semStr => {
                                                                const sem = Number(semStr);
                                                                const tts = yearGroup.semesters[sem];
                                                                return (
                                                                    <div key={sem} className="sem-sidebar-group">
                                                                        <div className="sem-sidebar-title">Semester {sem}</div>
                                                                        <div className="sections-list">
                                                                            {tts.map(tt => (
                                                                                <button
                                                                                    key={tt.id}
                                                                                    className={`section-sidebar-btn ${selectedTimetableId === tt.id ? 'active' : ''}`}
                                                                                    onClick={() => handleSelectTimetable(tt)}
                                                                                >
                                                                                    <span className="sec-title">Sec {tt.section?.name}</span>
                                                                                    <span className="status-pill">v{tt.version}</span>
                                                                                </button>
                                                                            ))}
                                                                        </div>
                                                                    </div>
                                                                );
                                                            })}
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    );
                                })}
                                {Object.keys(groupedFilteredTimetables).length === 0 && (
                                    <div className="empty-state">No timetables found.</div>
                                )}
                            </div>
                        )}

                            {viewMode === 'compare' && (
                                <div className="list-items-group checkbox-list">
                                    <div className="checkbox-list-header">
                                        <button 
                                            className="link-btn"
                                            onClick={() => setSelectedCompareTimetableIds(board.timetables.map(t => t.id))}
                                        >
                                            Select All
                                        </button>
                                        <button 
                                            className="link-btn"
                                            onClick={() => setSelectedCompareTimetableIds([])}
                                        >
                                            Clear All
                                        </button>
                                    </div>
                                    {filteredSections.map(tt => {
                                        const isChecked = selectedCompareTimetableIds.includes(tt.id);
                                        return (
                                            <label key={tt.id} className={`checkbox-item ${isChecked ? 'active' : ''}`}>
                                                <input 
                                                    type="checkbox" 
                                                    checked={isChecked}
                                                    onChange={() => {
                                                        setSelectedCompareTimetableIds(prev => 
                                                            prev.includes(tt.id) 
                                                                ? prev.filter(id => id !== tt.id) 
                                                                : [...prev, tt.id]
                                                        );
                                                    }}
                                                />
                                                <span className="checkbox-label">Section {tt.section?.name}</span>
                                            </label>
                                        );
                                    })}
                                </div>
                            )}

                            {viewMode === 'faculty' && (
                                <div className="list-items-group">
                                    {filteredFaculties.map(fac => (
                                        <button 
                                            key={fac.id}
                                            className={`list-item-btn ${selectedFacultyId === fac.id ? 'selected' : ''}`}
                                            onClick={() => setSelectedFacultyId(fac.id)}
                                        >
                                            <span className="item-label">{fac.name}</span>
                                            <span className="item-sub">{fac.faculty_id_code || 'No Code'}</span>
                                        </button>
                                    ))}
                                    {filteredFaculties.length === 0 && (
                                        <div className="empty-state">No faculties found.</div>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Highlighter Filter */}
                    <div className="panel-section highlighter-section">
                        <h3 className="section-title">Highlighter Filter</h3>
                        <div className="panel-search-box filter-search">
                            <Filter className="search-icon" size={14} />
                            <input 
                                type="text" 
                                placeholder="Highlight by Code/Faculty/Room..."
                                value={searchQuery}
                                onChange={e => setSearchQuery(e.target.value)}
                                className="search-input"
                            />
                        </div>
                    </div>
                </aside>
                )}

                {/* Center Schedule Workspace */}
                <main className="center-workspace">
                    {!selectedDept ? (
                        <div className="empty-workspace">
                            <Layers className="empty-icon" size={48} />
                            <h2>No Department Selected</h2>
                            <p>Please select a department from the top toolbar to load the scheduling workspace.</p>
                        </div>
                    ) : loadingBoard ? (
                        <div className="empty-workspace">
                            <RefreshCw className="empty-icon animate-spin" size={48} />
                            <h2>Loading schedules...</h2>
                            <p>Fetching visual timetable boards and timeslots.</p>
                        </div>
                    ) : board.timetables.length === 0 ? (
                        <div className="empty-workspace">
                            <AlertCircle className="empty-icon" size={48} />
                            <h2>No Schedules Found</h2>
                            <p>This department has no timetables. Click "Generate All" to create timetables with AI.</p>
                        </div>
                    ) : viewMode === 'faculty' && !selectedFacultyId ? (
                        <div className="empty-workspace">
                            <Users className="empty-icon" size={48} />
                            <h2>No Faculty Selected</h2>
                            <p>Select a faculty member from the left sidebar to view their active teaching timetable.</p>
                        </div>
                    ) : (
                        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
                            <div className="grid-scroll-wrap">
                                <table className="workspace-grid-table">
                                    <thead>
                                        <tr>
                                            <th className="time-header-col">Time Slot</th>
                                            {dayColumns.map(day => (
                                                <th key={day} className="day-header-col">{day}</th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {timeRows.map(row => {
                                            // Handle Break Separator row
                                            if (row.is_break) {
                                                return (
                                                    <tr key={`break-${row.start_time}`} className="grid-break-row">
                                                        <td className="time-col break-time">
                                                            <Clock3 size={12} />
                                                            <span>{row.start_time.slice(0, 5)} - {row.end_time.slice(0, 5)}</span>
                                                        </td>
                                                        <td colSpan={dayColumns.length} className="break-cell-span">
                                                            <div className="break-label-wrapper">
                                                                <Info size={13} />
                                                                <span>{row.label || 'Coffee/Lunch Break'}</span>
                                                            </div>
                                                        </td>
                                                    </tr>
                                                );
                                            }

                                            return (
                                                <tr key={`row-${row.start_time}`}>
                                                    <td className="time-col">
                                                        <Clock3 size={13} />
                                                        <span>{row.start_time.slice(0, 5)} - {row.end_time.slice(0, 5)}</span>
                                                    </td>
                                                    {dayColumns.map(day => {
                                                        const realSlot = board.time_slots.find(s => 
                                                            !s.is_break && 
                                                            s.day === day && 
                                                            s.start_time === row.start_time && 
                                                            s.end_time === row.end_time
                                                        );

                                                        if (!realSlot) {
                                                            return <td key={`empty-${day}-${row.start_time}`} className="board-cell-empty"></td>;
                                                        }

                                                        // RENDER TABS VIEW
                                                        if (viewMode === 'tabs') {
                                                            if (!activeSectionTimetable) return <td key={`tab-empty-${day}-${row.start_time}`}></td>;
                                                            
                                                            const entries = activeSectionTimetable.entries.filter(e => e.timeslot_id === realSlot.id);
                                                            const isConflict = (lastValidation?.error_slots || []).includes(realSlot.id);
                                                            const isWarning = (lastValidation?.warning_slots || []).includes(realSlot.id);
                                                            
                                                            // Highlight targets matching active section
                                                            const isTarget = activeDragEntry !== null && activeDragEntry.timetable_id === activeSectionTimetable.id;
                                                            const isDimmed = activeDragEntry !== null && activeDragEntry.timetable_id !== activeSectionTimetable.id;

                                                            return (
                                                                <DroppableCell 
                                                                    key={`slot-${activeSectionTimetable.id}-${realSlot.id}`} 
                                                                    id={`slot-${activeSectionTimetable.id}-${realSlot.id}`} 
                                                                    isConflict={isConflict}
                                                                    isWarning={isWarning}
                                                                    isTarget={isTarget}
                                                                    isDimmed={isDimmed}
                                                                >
                                                                    {entries.map(entry => (
                                                                        <DraggableEntryCard 
                                                                            key={entry.id} 
                                                                            entry={entry} 
                                                                            searchQuery={searchQuery}
                                                                            onLock={handleLockCard}
                                                                            onDelete={handleDeleteCard}
                                                                            isEditingMode={isEditingMode}
                                                                        />
                                                                    ))}
                                                                </DroppableCell>
                                                            );
                                                        }

                                                        // RENDER COMPARE MODE
                                                        if (viewMode === 'compare') {
                                                            return (
                                                                <td key={`compare-${realSlot.id}`} className="compare-cell-td">
                                                                    <div className="compare-lanes-container">
                                                                        {selectedCompareTimetableIds.map(ttId => {
                                                                            const tt = board.timetables.find(t => t.id === ttId);
                                                                            if (!tt) return null;
                                                                            
                                                                            const entries = tt.entries.filter(e => e.timeslot_id === realSlot.id);
                                                                            const isConflict = (lastValidation?.error_slots || []).includes(realSlot.id);
                                                                            const isWarning = (lastValidation?.warning_slots || []).includes(realSlot.id);
                                                                            
                                                                            const isTarget = activeDragEntry !== null && activeDragEntry.timetable_id === ttId;
                                                                            const isDimmed = activeDragEntry !== null && activeDragEntry.timetable_id !== ttId;

                                                                            return (
                                                                                <DroppableLane 
                                                                                    key={`lane-${ttId}-${realSlot.id}`}
                                                                                    id={`slot-${ttId}-${realSlot.id}`}
                                                                                    isConflict={isConflict}
                                                                                    isWarning={isWarning}
                                                                                    isTarget={isTarget}
                                                                                    isDimmed={isDimmed}
                                                                                    sectionName={`Sec ${tt.section?.name}`}
                                                                                >
                                                                                    {entries.map(entry => (
                                                                                        <DraggableEntryCard 
                                                                                            key={entry.id} 
                                                                                            entry={entry} 
                                                                                            searchQuery={searchQuery}
                                                                                            onLock={handleLockCard}
                                                                                            onDelete={handleDeleteCard}
                                                                                            isEditingMode={isEditingMode}
                                                                                        />
                                                                                    ))}
                                                                                </DroppableLane>
                                                                            );
                                                                        })}
                                                                    </div>
                                                                </td>
                                                            );
                                                        }

                                                        // RENDER FACULTY VIEW
                                                        if (viewMode === 'faculty') {
                                                            if (loadingFaculty) {
                                                                return (
                                                                    <td key={`fac-loading-${realSlot.id}`} className="board-cell-loading">
                                                                        <RefreshCw className="animate-spin opacity-40" size={14} />
                                                                    </td>
                                                                );
                                                            }

                                                            const fEntries = resolvedFacultyEntries.filter((e: any) => e.current_timeslot_id === realSlot.id);
                                                            const isConflict = fEntries.some((e: any) => (lastValidation?.error_slots || []).includes(e.current_timeslot_id));
                                                            const isWarning = fEntries.some((e: any) => (lastValidation?.warning_slots || []).includes(e.current_timeslot_id));
                                                            
                                                            // Highlight cell if activeDragEntry is defined (we dynamically set droppable slot ID to matches section)
                                                            const droppableId = activeDragEntry 
                                                                ? `slot-${activeDragEntry.timetable_id}-${realSlot.id}` 
                                                                : `slot-dummy-${realSlot.id}`;
                                                            
                                                            const isTarget = activeDragEntry !== null;

                                                            return (
                                                                <DroppableCell 
                                                                    key={`fac-slot-${realSlot.id}`} 
                                                                    id={droppableId} 
                                                                    isConflict={isConflict}
                                                                    isWarning={isWarning}
                                                                    isTarget={isTarget}
                                                                >
                                                                    {fEntries.map((entry: any) => {
                                                                        const isLocal = board.timetables
                                                                            .flatMap((t: any) => t.entries)
                                                                            .some(e => e.id === entry.id);

                                                                        return (
                                                                            <DraggableEntryCard 
                                                                                key={entry.id} 
                                                                                entry={{
                                                                                    ...entry,
                                                                                    subject: { code: entry.subject_code, name: entry.subject_name },
                                                                                    faculty: { name: facultyTimetable?.faculty_name || 'Faculty' },
                                                                                    section: { name: entry.section_name }
                                                                                }} 
                                                                                searchQuery={searchQuery}
                                                                                onLock={isLocal ? handleLockCard : undefined}
                                                                                onDelete={isLocal ? handleDeleteCard : undefined}
                                                                                isEditingMode={isEditingMode}
                                                                            />
                                                                        );
                                                                    })}
                                                                </DroppableCell>
                                                            );
                                                        }

                                                        return null;
                                                    })}
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                            
                            {!isEditingMode && board.timetables.length > 0 && (
                                <div className="workspace-bottom-bar">
                                    <button 
                                        className="bottom-btn btn-edit-workspace"
                                        onClick={() => setIsEditingMode(true)}
                                        disabled={board.timetables.length === 0}
                                    >
                                        <Sparkles size={16} />
                                        <span>Edit in Visual Scheduler</span>
                                    </button>
                                    <button 
                                        className="bottom-btn btn-approve-workspace"
                                        onClick={handleApprove}
                                        disabled={saving || !selectedTimetableId}
                                    >
                                        <CheckCircle2 size={16} />
                                        <span>Approve</span>
                                    </button>
                                </div>
                            )}
                        </DndContext>
                    )}
                </main>

                {/* Right Inspector Sidebar */}
                <aside className="right-panel">
                    {/* Conflict Inspector */}
                    <div className="panel-section border-bottom">
                        <h3 className="section-title">Conflict Inspector</h3>
                        {lastValidation ? (
                            <div className="inspector-box">
                                <div className={`validation-status-header ${lastValidation.status === 'PASS' ? 'status-pass' : 'status-fail'}`}>
                                    {lastValidation.status === 'PASS' ? (
                                        <>
                                            <CheckCircle2 size={16} />
                                            <span>Validation Passed</span>
                                        </>
                                    ) : (
                                        <>
                                            <AlertTriangle size={16} />
                                            <span>Conflicts Detected ({lastValidation.errors?.length || 0})</span>
                                        </>
                                    )}
                                </div>
                                <div className="messages-list scrollbar-accent">
                                    {(lastValidation.errors || []).map((e: string, i: number) => (
                                        <div key={`err-${i}`} className="message-item message-error">
                                            <AlertCircle size={13} />
                                            <span>{e}</span>
                                        </div>
                                    ))}
                                    {(lastValidation.warnings || []).map((w: string, i: number) => (
                                        <div key={`warn-${i}`} className="message-item message-warning">
                                            <AlertTriangle size={13} />
                                            <span>{w}</span>
                                        </div>
                                    ))}
                                    {(!lastValidation.errors?.length && !lastValidation.warnings?.length) && (
                                        <p className="no-message-muted">No warnings or errors for this schedule version.</p>
                                    )}
                                </div>
                            </div>
                        ) : (
                            <div className="inspector-box empty">
                                <Info size={16} />
                                <p>Drag a card or make edits to trigger live constraint validation checks.</p>
                            </div>
                        )}
                    </div>

                    {/* Move Suggestions */}
                    <div className="panel-section border-bottom">
                        <h3 className="section-title">Smart Move Suggestions</h3>
                        <div className="suggestions-list scrollbar-accent">
                            {suggestions.length > 0 ? (
                                suggestions.map((s, i) => (
                                    <div key={i} className="suggestion-item">
                                        <div className="suggestion-meta">
                                            <span className="suggestion-time">{s.day} • {s.start_time?.slice(0, 5)}</span>
                                            <span className="suggestion-reason">{s.reason}</span>
                                        </div>
                                    </div>
                                ))
                            ) : (
                                <p className="no-message-muted">No alternative suggestions available. Grid is optimized.</p>
                            )}
                        </div>
                    </div>

                    {/* Version History Log */}
                    <div className="panel-section flex-grow">
                        <h3 className="section-title">Version History</h3>
                        <div className="history-logs-container scrollbar-accent">
                            {selectedTimetableId ? (
                                historyEvents.length > 0 ? (
                                    historyEvents.map((item: any) => (
                                        <div key={item.id} className="history-log-item">
                                            <div className="log-marker">
                                                <History size={11} className="log-icon" />
                                            </div>
                                            <div className="log-content">
                                                <div className="log-header-info">
                                                    <span className="log-action">{item.event_type}</span>
                                                    <span className="log-version">v{item.version}</span>
                                                </div>
                                                <span className="log-time">
                                                    {new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                                </span>
                                            </div>
                                        </div>
                                    ))
                                ) : (
                                    <p className="no-message-muted">No revision history events logged yet.</p>
                                )
                            ) : (
                                <p className="no-message-muted">Select a section in the left panel to load its history log.</p>
                            )}
                        </div>
                    </div>
                </aside>
            </div>

            {/* Global Error Banner */}
            {error && (
                <div className="global-error-banner" onClick={() => setError(null)}>
                    <AlertTriangle size={15} />
                    <span>{error}</span>
                    <button className="close-banner" onClick={() => setError(null)}>×</button>
                </div>
            )}
        </div>
    );
};

export default VisualTimetables;
