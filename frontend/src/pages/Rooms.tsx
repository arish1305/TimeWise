import { useState, useEffect } from 'react';
import api from '../api/axios';
import { Plus, Trash2, Edit2, Box } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface Room {
    id: number;
    room_number: string;
    capacity: number;
    room_type: string;
}

const Rooms = () => {
    const [rooms, setRooms] = useState<Room[]>([]);
    // const [loading, setLoading] = useState(false); // Unused


    // Form
    const [showForm, setShowForm] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [newRoom, setNewRoom] = useState({ room_number: '', capacity: 60, room_type: 'CLASSROOM' });

    useEffect(() => {
        fetchRooms();
    }, []);

    const fetchRooms = async () => {
        try {
            const res = await api.get('/admin/rooms');
            setRooms(res.data);
        } catch (err) { console.error(err); }
    };

    const saveRoom = async () => {
        try {
            if (editingId) {
                await api.put(`/admin/rooms/${editingId}`, newRoom); // Note: Put endpoint might need to be verified if strictly exists or uses same structure
                // Logic check: Backend might not have PUT /rooms/{id} implemented in my memory? 
                // Wait, I saw create_room and read_rooms in admin.py step 380, but I DID NOT see update_room or delete_room implementation! 
                // Implementation Plan Step 8 implies I should create the page, but if backend is missing endpoints I should implement them first/concurrently?
                // Actually looking back at Step 380 admin.py content (lines 120-132), it ONLY has Create and Read.
                // I will add Delete and Update to backend as well to make this fully functional.
                // For now, I will write the frontend assuming they exist or I will add them next.
            } else {
                await api.post('/admin/rooms', newRoom);
            }
            setShowForm(false);
            setEditingId(null);
            setNewRoom({ room_number: '', capacity: 60, room_type: 'CLASSROOM' });
            fetchRooms();
        } catch (err: any) {
            console.error(err);
            alert("Failed to save room.");
        }
    };

    const deleteRoom = async (id: number) => {
        if (!window.confirm("Delete this room?")) return;
        try {
            // Again, Backend verification needed for DELETE endpoint
            await api.delete(`/admin/rooms/${id}`);
            fetchRooms();
        } catch (err) { console.error(err); alert("Failed to delete room (Endpoint might be missing)"); }
    };

    const startEdit = (room: Room) => {
        setNewRoom({ room_number: room.room_number, capacity: room.capacity, room_type: room.room_type });
        setEditingId(room.id);
        setShowForm(true);
    };

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
                <h1 style={{ fontSize: '2rem', fontWeight: 800 }}>Rooms</h1>
                <button className="btn btn-primary" onClick={() => {
                    setEditingId(null);
                    setNewRoom({ room_number: '', capacity: 60, room_type: 'CLASSROOM' });
                    setShowForm(true);
                }}>
                    <Plus size={20} /> Add Room
                </button>
            </div>

            <AnimatePresence>
                {showForm && (
                    <motion.div
                        initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}
                        className="card" style={{ marginBottom: '2rem', borderLeft: '4px solid var(--primary-500)' }}
                    >
                        <h3>{editingId ? 'Edit Room' : 'New Room'}</h3>
                        <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem', alignItems: 'center' }}>
                            <input className="input-field" placeholder="Room Number (e.g. 101)" value={newRoom.room_number} onChange={e => setNewRoom({ ...newRoom, room_number: e.target.value })} />
                            <input type="number" className="input-field" placeholder="Capacity" value={newRoom.capacity} onChange={e => setNewRoom({ ...newRoom, capacity: parseInt(e.target.value) })} style={{ width: 100 }} />
                            <select className="input-field" value={newRoom.room_type} onChange={e => setNewRoom({ ...newRoom, room_type: e.target.value })} style={{ width: 150 }}>
                                <option value="CLASSROOM">Classroom</option>
                                <option value="LAB">Lab</option>
                                <option value="SEMINAR_HALL">Seminar Hall</option>
                            </select>
                            <button className="btn btn-primary" onClick={saveRoom}>Save</button>
                            <button className="btn" onClick={() => setShowForm(false)}>Cancel</button>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: '1.5rem' }}>
                {rooms.map(room => (
                    <motion.div
                        layout
                        key={room.id}
                        className="card"
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                    >
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <div style={{
                                    width: 32, height: 32, borderRadius: '50%',
                                    background: 'var(--primary-100)', color: 'var(--primary-600)',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center'
                                }}>
                                    <Box size={16} />
                                </div>
                                <span style={{ fontWeight: 700, fontSize: '1.1rem' }}>{room.room_number}</span>
                            </div>
                            <div style={{ display: 'flex', gap: '0.25rem' }}>
                                {/* Edit/Delete assuming endpoints will exist */}
                                <button className="btn" style={{ padding: '0.3rem', color: 'var(--text-muted)' }} onClick={() => startEdit(room)} disabled>
                                    <Edit2 size={16} />
                                </button>
                                <button className="btn" style={{ padding: '0.3rem', color: 'var(--error-color)' }} onClick={() => deleteRoom(room.id)} disabled>
                                    <Trash2 size={16} />
                                </button>
                            </div>
                        </div>

                        <div style={{ fontSize: '0.9rem', color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                            <div>Type: <span style={{ fontWeight: 600, color: 'var(--text-color)' }}>{room.room_type}</span></div>
                            <div>Capacity: <span style={{ fontWeight: 600, color: 'var(--text-color)' }}>{room.capacity}</span> Students</div>
                        </div>
                    </motion.div>
                ))}
            </div>
        </div>
    );
};

export default Rooms;
