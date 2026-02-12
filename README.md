# Attendance By Face Detection

A comprehensive web-based attendance management system that utilizes face recognition technology to automate student attendance tracking. This application is designed for educational institutions to streamline attendance processes, manage student records, and handle leave requests efficiently.

## Features

- **Face Recognition Attendance**: Automated attendance marking using facial recognition technology
- **Dual User Roles**: Separate dashboards for administrators and students
- **Student Management**: Add, edit, and view student information
- **Attendance Tracking**: View attendance records and reports
- **Leave Management**: Students can request leaves, admins can approve/reject requests
- **Holiday Management**: Configure and manage holiday schedules
- **Mobile Responsive**: Optimized for mobile devices for on-the-go access
- **Real-time Notifications**: Audio feedback for attendance marking

## Technologies Used

- **Backend**: Python, Flask
- **Database**: SQLite (local development), MySQL (production)
- **Face Recognition**: OpenCV, face_recognition library
- **Frontend**: HTML, CSS, JavaScript, Bootstrap
- **Deployment**: Ready for deployment on platforms like Heroku, Vercel, or AWS

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Nithin123t/Attendance_By_Face_Detection.git
   cd Attendance_By_Face_Detection
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up the database:
   - For local development (SQLite): The app will automatically create the database
   - For production (MySQL): Update the database configuration in `database.py`

5. Run the application:
   ```bash
   python app.py
   ```

6. Open your browser and navigate to `http://localhost:5000`

## Usage

### For Administrators:
- Login with admin credentials
- Manage students: Add new students, edit existing ones
- View attendance records
- Manage leave requests
- Configure holidays

### For Students:
- Login with student credentials
- View personal attendance records
- Request leaves
- Access dashboard for quick overview

### Taking Attendance:
- Navigate to the "Take Attendance" page
- The system will use the camera to recognize faces and mark attendance automatically
- Mobile-friendly interface for scanning on the go

## Project Structure

```
Attendance_By_Face_Detection/
├── app.py                 # Main Flask application
├── database.py            # Database connection and operations
├── face_utils.py          # Face recognition utilities
├── auto_absent.py         # Automated absent marking script
├── requirements.txt       # Python dependencies
├── TODO.md               # Project tasks and progress
├── dataset/              # Face recognition training data
├── templates/            # HTML templates
├── static/               # CSS, JS, and media files
├── figma-mockups/        # UI design mockups
└── README.md             # Project documentation
```

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contact

For questions or support, please open an issue on GitHub or contact the project maintainer.

---

**Note**: This application uses face recognition technology. Ensure compliance with privacy laws and obtain necessary consents when deploying in production environments.
