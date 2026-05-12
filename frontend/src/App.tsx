import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Login from './pages/Login';
import AdminDashboard from './pages/AdminDashboard';
import Departments from './pages/Departments';
import Faculty from './pages/Faculty';
import Timetables from './pages/Timetables';
import FacultyTimetable from './pages/FacultyTimetable';
import AdminFacultyTimetable from './pages/AdminFacultyTimetable';
import Layout from './components/Layout';

const RoleRoute: React.FC<{ children: React.ReactNode; allowedRoles: Array<'ADMIN' | 'FACULTY'> }> = ({ children, allowedRoles }) => {
  const { isAuthenticated, role, isLoading } = useAuth();

  if (isLoading) {
    return <div style={{ padding: '2rem' }}>Loading...</div>;
  }

  if (!isAuthenticated || !role) {
    return <Navigate to="/login" replace />;
  }

  if (!allowedRoles.includes(role)) {
    return <Navigate to={role === 'ADMIN' ? '/admin' : '/faculty'} replace />;
  }

  return <>{children}</>;
};

const HomeRedirect = () => {
  const { isAuthenticated, role, isLoading } = useAuth();

  if (isLoading) {
    return <div style={{ padding: '2rem' }}>Loading...</div>;
  }

  if (!isAuthenticated || !role) {
    return <Navigate to="/login" replace />;
  }

  return <Navigate to={role === 'ADMIN' ? '/admin' : '/faculty'} replace />;
};

function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/login" element={<Login />} />

          <Route path="/admin" element={
            <RoleRoute allowedRoles={['ADMIN']}>
              <Layout />
            </RoleRoute>
          }>
            <Route index element={<AdminDashboard />} />
            <Route path="departments" element={<Departments />} />
            <Route path="faculty" element={<Faculty />} />
            <Route path="faculty-timetable" element={<AdminFacultyTimetable />} />
            <Route path="timetables" element={<Timetables />} />
          </Route>

          <Route path="/faculty" element={
            <RoleRoute allowedRoles={['FACULTY']}>
              <Layout />
            </RoleRoute>
          }>
            <Route index element={<FacultyTimetable />} />
          </Route>

          <Route path="/" element={<HomeRedirect />} />
          <Route path="*" element={<HomeRedirect />} />
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;
