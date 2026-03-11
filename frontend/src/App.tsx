import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
// import Login from './pages/Login'; // Removed
import AdminDashboard from './pages/AdminDashboard';
import Departments from './pages/Departments';
import Faculty from './pages/Faculty';
import Subjects from './pages/Subjects';
import Rooms from './pages/Rooms';
import TimeSlots from './pages/TimeSlots';
import Timetables from './pages/Timetables';
import Layout from './components/Layout';

const PrivateRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return <>{children}</>;
};

function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          {/* <Route path="/login" element={<Login />} /> */}

          <Route path="/admin" element={
            <PrivateRoute>
              <Layout />
            </PrivateRoute>
          }>
            <Route index element={<AdminDashboard />} />
            <Route path="departments" element={<Departments />} />
            <Route path="faculty" element={<Faculty />} />
            <Route path="subjects" element={<Subjects />} />
            <Route path="rooms" element={<Rooms />} />
            <Route path="timeslots" element={<TimeSlots />} />
            <Route path="timetables" element={<Timetables />} />
          </Route>

          {/* Redirect root to admin */}
          <Route path="/" element={<Navigate to="/admin" />} />

          {/* Catch all redirect to admin */}
          <Route path="*" element={<Navigate to="/admin" />} />
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;
