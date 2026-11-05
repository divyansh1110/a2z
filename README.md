# Planly — Striver's A2Z DSA Study Planner

Planly is an intelligent, clean, and interactive DSA study scheduler built with **Flask** and **HTML/CSS/JS** based on Striver's A2Z DSA Sheet (`data/full_dsa_sheet_syllabus.json`).

---

## 📁 Project Structure

```
d:\project\a2z\
├── .env                              # Environment variables (Mongo URI, DB name, etc.)
├── .env.example                      # Example environment variable template
├── data\
│   └── full_dsa_sheet_syllabus.json  # 495 problems across 20 topics
├── logs\
│   └── app.log                       # Application event and error logs
├── src\
│   ├── static\
│   │   ├── app.js                    # Interactive client frontend
│   │   └── style.css                 # Clean modern dark theme
│   ├── templates\
│   │   └── index.html                # Single-page UI
│   ├── __init__.py
│   ├── app.py                        # Flask routes & REST APIs
│   ├── config.py                     # Environment variables loader
│   ├── logger.py                     # Rotating file logger (writes to logs/app.log)
│   ├── planner.py                    # Syllabus scheduling & realignment algorithms
│   └── storage.py                    # Pure MongoDB storage configured via .env
├── tests\
│   └── test_planly.py                # Unit and integration test suite
├── run.py                            # Application entry point
├── pyproject.toml
└── README.md
```

---

## ⚙️ Configuration (`.env`)

Database connection and server settings are loaded from `.env`:

```env
MONGO_URI=mongodb://localhost:27017/
MONGO_DB_NAME=planly_db
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
FLASK_DEBUG=True
```

---

## ✨ Features

- **Weekly Availability Scheduler**:
  - Configure which days of the week you are free (Monday through Sunday).
  - Set how many hours you can commit on each active day.
  - Automatically schedules all **495 problems** across active study days, with designated rest days.

- **Daily Focus View**:
  - Displays the exact topics and problems scheduled for today.
  - Interactive checkboxes to mark problems as completed in real time.
  - Direct links to **LeetCode**, **YouTube Tutorials**, and **TakeUForward Solution Articles**.
  - "Mark All Done" quick action for the day.

- **Mark for Revision**:
  - Dedicated **Revise** bookmark button and badge on every problem across Today's Focus, Full Schedule, and Syllabus Progress views.
  - Real-time revision counter in the Quick Stats Bar.
  - Quick filters in Full Schedule (**Revision Only**) and Syllabus Progress (**For Revision**) to immediately isolate bookmarked problems for review.
  - Revision status is stored in MongoDB (`problem_progress` collection and study plan) and preserved independently of completion status.

- **Pause & Break System**:
  - Going on break? Click **Pause Plan**.
  - When you return, click **Resume Plan**, select your restart date, and all remaining incomplete tasks shift forward automatically!
  - **Re-align**: Catch up effortlessly if you missed a day or two.
  - **Reset Progress & Start from 0**: Easily restart your preparation from 0% at any time. Resets all 495 problems back to incomplete, clears checkmarks, and optionally shifts schedule dates to start fresh from today or keeps your calendar timeline.

- **Storage**:
  - Pure **MongoDB** running on `mongodb://localhost:27017/` (Database: `planly_db`).
  - No fallback SQLite database used.
  - Live connection status pill and alert banner in the UI.

- **Logging**:
  - All application lifecycle events, API requests, plan generations, and errors are saved to `logs/app.log`.

---

## 🚀 Getting Started

### 1. Ensure MongoDB is Running
Make sure your local MongoDB service is running on default port `27017`:
```bash
mongod
```

### 2. Run the Application
You can run either:
```bash
python run.py
```
or
```bash
python src/app.py
```

### 3. Open in Browser
Navigate to:
```
http://127.0.0.1:5000
```
