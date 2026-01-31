import requests
import json

BASE_URL = "http://localhost:8000"

def test_generate():
    # 1. Login
    print("Logging in...")
    try:
        resp = requests.post(f"{BASE_URL}/auth/login", data={
            "username": "admin",
            "password": "admin123"
        })
        if resp.status_code != 200:
            print("Login Failed:", resp.text)
            return
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("Login Success.")
        
        # 2. Get Sections (knowing structure)
        # First get Department CSE
        resp = requests.get(f"{BASE_URL}/admin/departments", headers=headers)
        depts = resp.json()
        cse = next((d for d in depts if d["code"] == "CSE"), None)
        if not cse:
            print("CSE Department not found")
            return
        print(f"Found Dept: {cse['name']} (ID: {cse['id']})")
        
        # Get Academic Years
        resp = requests.get(f"{BASE_URL}/admin/academic-years?department_id={cse['id']}", headers=headers)
        years = resp.json()
        year2 = next((y for y in years if y["name"] == "Year 2"), None)
        if not year2:
            print("Year 2 not found")
            return
        print(f"Found Year: {year2['name']} (ID: {year2['id']})")
        
        # Get Sections
        resp = requests.get(f"{BASE_URL}/admin/sections?year_id={year2['id']}", headers=headers)
        sections = resp.json()
        sec_a = next((s for s in sections if s["name"] == "A"), None)
        if not sec_a:
            print("Section A not found")
            return
        print(f"Found Section: {sec_a['name']} (ID: {sec_a['id']})")
        
        # Check Subjects
        print("Checking Subjects...")
        resp = requests.get(f"{BASE_URL}/admin/subjects?department_id={cse['id']}", headers=headers)
        subjs = resp.json()
        sem3_subjs = [s for s in subjs if s['semester'] == 3]
        print(f"Semester 3 Subjects: {len(sem3_subjs)}")
        for s in sem3_subjs:
            print(f"  {s['code']} ({s['name']}) - {s['weekly_hours']} hours")
        
        # 3. Generate Timetable
        print("Generating Timetable...")
        payload = {
            "section_id": sec_a["id"],
            "semester": 3 # Year 2 usually Sem 3 or 4
        }
        resp = requests.post(f"{BASE_URL}/timetables/generate", json=payload, headers=headers)
        if resp.status_code == 200:
            tt = resp.json()
            print("Timetable Generated Successfully!")
            print(f"ID: {tt['id']}, Status: {tt['status']}")
            print(f"Entries: {len(tt['entries'])}")
            for entry in tt['entries']:
                # entry.subject, entry.faculty (might be dicts or IDs depending on schema)
                # entry is Pydantic model response
                subj = entry.get('subject', {})
                fac = entry.get('faculty', {}) or {'name': 'TBD'}
                print(f"  Slot {entry['timeslot_id']}: {subj.get('code','?')} - {fac.get('name','TBD')}")
        else:
            print("Generation Failed:", resp.status_code, resp.text)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_generate()
