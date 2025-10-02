## ISHAARA - SPEECH TO INDIAN SIGN LANGUAGE CONVERSION USING ANIMATED AVATARS
This is a B.Tech final year project that serves as a proof-of-concept for a real-time communication tool designed to bridge the gap between hearing individuals and the Deaf community. The application captures spoken English, transcribes it to text, translates the text into a grammatically appropriate Indian Sign Language (ISL) gloss, and renders the translation as a sequence of animations on a 3D avatar in a web browser.
This project sits at the intersection of Artificial Intelligence, Natural Language Processing (NLP), and real-time Computer Graphics.

## Core Features
- **Real-Time Audio Transcription**: Captures live audio from the user's microphone and uses a state-of-the-art AI model for accurate speech-to-text conversion.
- **Grammatical ISL Translation**: Implements a sophisticated NLP engine to convert English sentence structures into the correct ISL gloss, moving beyond simple word-for-word mapping.
- **3D Avatar Animation**: Renders a 3D avatar in the browser and plays a sequence of sign language animations in real-time.
- **Scalable Architecture**: Utilizes a "lazy loading" mechanism for animations, allowing the system's vocabulary to expand to thousands of words without performance degradation.
- **Animation Blending**: Employs cross-fading between animations to produce a fluid, natural, and co-articulated motion for the avatar.

## Technology Stack

### Frontend (Client) 
- HTML5, CSS3, JavaScript- For the user interface and core application logic.
- Three.js - A powerful 3D graphics library for rendering the avatar and animations.

### Backend (Server) 
- Python 3 - The core language for all AI and server-side logic
- Flask - A lightweight web framework to create the API endpoint.
- spaCy - An advanced NLP library for grammatical parsing and translation logic.
- faster-whisper - An efficient implementation of OpenAI's Whisper model for speech-to-text.

### 3D Asset Pipeline 
- Ready Player Me - For generating high-quality, standardized 3D avatars.
- Blender - For creating all custom ISL sign animations.

## Setup and Installation

### Clone the Repository
```
git clone https://github.com/19rishabh/ishaara-speech-to-sign-animator.git
cd ishaara-speech-to-sign-animator
cd backend
```
### Create a Python virtual environment
```
python -m venv ishaaravenv
```
### Activate the virtual environment
```
On Windows: venv\Scripts\activate
On macOS/Linux: source venv/bin/activate
```
### Install the required Python libraries from requirements.txt
```
pip install -r requirements.txt
```
### Download the necessary spaCy English language model
```
python -m spacy download en_core_web_sm
```
## How to Run the Application

### Terminal 1: Start the Backend Server
Open a new terminal.

### Navigate to the backend directory.
```
cd backend
```
Activate the virtual environment if it's not already active.

### Run the Flask application:
```
flask run
```
### Terminal 2: Start the Frontend Server
Open a second, separate terminal.

### Navigate to the frontend directory.
```
cd frontend
```
### Start the simple Python HTTP server:
```
python -m http.server
```
### Accessing the Application
Open a modern web browser (like Chrome or Firefox).
Navigate to the following address: http://localhost:8000
