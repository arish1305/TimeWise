import { useState, useEffect } from 'react';
import api from '../api/axios';
import { Plus, Trash2, Edit2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { formatTimeRange12Hour } from '../utils/timeFormat';
import TimePicker12 from '../components/TimePicker12';

interface TimeSlot {
    id: number;
    day: string;
    start_time: string;
    end_time: string;
    is_break: boolean;
    label?: string;
}

const TimeSlots = () => {
    const [slots, setSlots] = useState<TimeSlot[]>([]);
    // const [loading, setLoading] = useState(false);

    const [showForm, setShowForm] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [newSlot, setNewSlot] = useState({
        day: 'Monday',
        start_time: '09:00',
        end_time: '10:00',
        is_break: false,
        label: ''
    });

    const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

    useEffect(() => {
        fetchSlots();
    }, []);

    const fetchSlots = async () => {
        try {
            const res = await api.get('/admin/timeslots');
            setSlots(res.data);
        } catch (err) { console.error(err); }
    };

    const saveSlot = async () => {
        try {
            const payload = {
                ...newSlot,
                start_time: newSlot.start_time.length === 5 ? newSlot.start_time + ':00' : newSlot.start_time,
                end_time: newSlot.end_time.length === 5 ? newSlot.end_time + ':00' : newSlot.end_time
            };

            if (editingId) {
                await api.put(`/admin/timeslots/${editingId}`, payload);
            } else {
                await api.post('/admin/timeslots', payload);
            }
            setShowForm(false);
            setEditingId(null);
            setNewSlot({ day: 'Monday', start_time: '09:00', end_time: '10:00', is_break: false, label: '' });
            fetchSlots();
        } catch (err: any) {
            console.error(err);
            alert("Failed to save time slot. Ensure End Time > Start Time.");
        }
    };

    const deleteSlot = async (id: number) => {
        if (!window.confirm("Delete this time slot?")) return;
        try {
            await api.delete(`/admin/timeslots/${id}`);
            fetchSlots();
        } catch (err) { console.error(err); alert("Failed to delete slot"); }
    };

    const startEdit = (slot: TimeSlot) => {
        // Slot times come back as "09:00:00" from backend usually
        setNewSlot({
            day: slot.day,
            start_time: slot.start_time.substring(0, 5),
            end_time: slot.end_time.substring(0, 5),
            is_break: slot.is_break,
            label: slot.label || ''
        });
        setEditingId(slot.id);
        setShowForm(true);
    };

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
                <h1 style={{ fontSize: '2rem', fontWeight: 800 }}>Time Slots</h1>
                <button className="btn btn-primary" onClick={() => {
                    setEditingId(null);
                    setNewSlot({ day: 'Monday', start_time: '09:00', end_time: '10:00', is_break: false, label: '' });
                    setShowForm(true);
                }}>
                    <Plus size={20} /> Add Time Slot
                </button>
            </div>

            <AnimatePresence>
                {showForm && (
                    <motion.div
                        initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}
                        className="card" style={{ marginBottom: '2rem', borderLeft: '4px solid var(--primary-500)' }}
                    >
                        <h3>{editingId ? 'Edit Slot' : 'New Slot'}</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '1rem', marginTop: '1rem', alignItems: 'end' }}>
                            <div>
                                <label style={{ fontSize: '0.8rem', fontWeight: 600 }}>Day</label>
                                <select className="input-field" value={newSlot.day} onChange={e => setNewSlot({ ...newSlot, day: e.target.value })} style={{ width: '100%' }}>
                                    {days.map(d => <option key={d} value={d}>{d}</option>)}
                                </select>
                            </div>
                            <div>
                                <label style={{ fontSize: '0.8rem', fontWeight: 600 }}>Start</label>
                                <TimePicker12 value={newSlot.start_time} onChange={value => setNewSlot({ ...newSlot, start_time: value })} />
                            </div>
                            <div>
                                <label style={{ fontSize: '0.8rem', fontWeight: 600 }}>End</label>
                                <TimePicker12 value={newSlot.end_time} onChange={value => setNewSlot({ ...newSlot, end_time: value })} />
                            </div>
                            <div>
                                <label style={{ fontSize: '0.8rem', fontWeight: 600 }}>Label (Optional)</label>
                                <input className="input-field" placeholder="e.g. Lunch" value={newSlot.label} onChange={e => setNewSlot({ ...newSlot, label: e.target.value })} style={{ width: '100%' }} />
                            </div>
                            <div style={{ paddingBottom: '0.8rem' }}>
                                <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                                    <input type="checkbox" checked={newSlot.is_break} onChange={e => setNewSlot({ ...newSlot, is_break: e.target.checked })} />
                                    <span>Is Break?</span>
                                </label>
                            </div>
                        </div>
                        <div style={{ marginTop: '1rem', display: 'flex', gap: '1rem' }}>
                            <button className="btn btn-primary" onClick={saveSlot}>Save</button>
                            <button className="btn" onClick={() => setShowForm(false)}>Cancel</button>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            <div className="card">
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr style={{ borderBottom: '2px solid var(--border-light)', textAlign: 'left' }}>
                            <th style={{ padding: '1rem' }}>Day</th>
                            <th style={{ padding: '1rem' }}>Time</th>
                            <th style={{ padding: '1rem' }}>Label</th>
                            <th style={{ padding: '1rem' }}>Type</th>
                            <th style={{ padding: '1rem', textAlign: 'right' }}>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {slots.length === 0 ? (
                            <tr><td colSpan={5} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>No time slots defined.</td></tr>
                        ) : (
                            slots.sort((a, b) => a.day.localeCompare(b.day) || a.start_time.localeCompare(b.start_time)).map(slot => (
                                <tr key={slot.id} style={{ borderBottom: '1px solid var(--border-light)' }}>
                                    <td style={{ padding: '1rem' }}>{slot.day}</td>
                                    <td style={{ padding: '1rem', fontFamily: 'monospace', fontWeight: 600 }}>
                                        {formatTimeRange12Hour(slot.start_time, slot.end_time)}
                                    </td>
                                    <td style={{ padding: '1rem' }}>{slot.label || '-'}</td>
                                    <td style={{ padding: '1rem' }}>
                                        {slot.is_break ? (
                                            <span style={{ background: 'var(--warning-light)', color: 'var(--warning-color)', padding: '0.2rem 0.5rem', borderRadius: 4, fontSize: '0.8rem', fontWeight: 600 }}>Break</span>
                                        ) : (
                                            <span style={{ background: 'var(--success-light)', color: 'var(--success-color)', padding: '0.2rem 0.5rem', borderRadius: 4, fontSize: '0.8rem', fontWeight: 600 }}>Class</span>
                                        )}
                                    </td>
                                    <td style={{ padding: '1rem', textAlign: 'right' }}>
                                        <button className="btn" style={{ padding: '0.3rem', color: 'var(--text-muted)' }} onClick={() => startEdit(slot)}>
                                            <Edit2 size={16} />
                                        </button>
                                        <button className="btn" style={{ padding: '0.3rem', color: 'var(--error-color)' }} onClick={() => deleteSlot(slot.id)}>
                                            <Trash2 size={16} />
                                        </button>
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default TimeSlots;
