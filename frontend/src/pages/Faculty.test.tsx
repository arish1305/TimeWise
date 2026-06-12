import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import FacultyManager from './Faculty';
import api from '../api/axios';

vi.mock('../api/axios', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
        put: vi.fn(),
        delete: vi.fn(),
    }
}));

describe('Faculty availability grid', () => {
    it('cycles availability cell and saves bulk update', async () => {
        const mockedApi = api as any;
        mockedApi.get.mockImplementation((url: string) => {
            if (url === '/admin/faculty') {
                return Promise.resolve({
                    data: [{
                        id: 1,
                        name: 'Dr. Availability',
                        faculty_id_code: 'FAC1',
                        faculty_type: 'ASSISTANT_PROFESSOR',
                        min_hours_per_week: 5,
                        max_hours_per_week: 18,
                        departments: [{ id: 10, name: 'AI', code: 'AI' }],
                        qualified_subjects: [],
                    }]
                });
            }
            if (url === '/admin/subjects') return Promise.resolve({ data: [] });
            if (url === '/admin/academic-years') return Promise.resolve({ data: [] });
            if (url === '/admin/sections') return Promise.resolve({ data: [] });
            if (url === '/admin/departments') return Promise.resolve({ data: [{ id: 10, name: 'AI', code: 'AI' }] });
            if (url === '/faculty/1/availability') {
                return Promise.resolve({
                    data: {
                        faculty_id: 1,
                        entries: [{
                            timeslot_id: 101,
                            status: 'AVAILABLE',
                            day: 'Monday',
                            start_time: '09:00:00',
                            end_time: '10:00:00',
                            department_id: 10,
                        }]
                    }
                });
            }
            return Promise.resolve({ data: [] });
        });
        mockedApi.post.mockResolvedValue({ data: {} });

        render(<FacultyManager />);

        await screen.findByText('Dr. Availability');
        fireEvent.click(screen.getByTitle('Assign Subjects'));

        await screen.findByText('Availability Grid');
        fireEvent.click(screen.getAllByRole('button', { name: 'Available' })[0]);

        await waitFor(() => {
            expect(mockedApi.post).toHaveBeenCalledWith('/faculty/1/availability', {
                entries: [{ timeslot_id: 101, status: 'PREFERRED' }]
            });
        });
    });
});
