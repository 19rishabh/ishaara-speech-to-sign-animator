import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

let scene, camera, renderer, model, mixer, clock;
const animationActions = {}; // This will act as our cache for loaded animations
let animationQueue = [];
let isPlayingAnimation = false;

// --- Audio Recording Variables ---
let mediaRecorder;
let audioChunks = [];
let isRecording = false;

// --- DOM ELEMENTS ---
const statusElement = document.getElementById('status');
const transcriptionElement = document.getElementById('transcription');
const micBtn = document.getElementById('mic-btn');

init();

function init() {
    // --- Basic Scene Setup ---
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0xeeeeee);
    clock = new THREE.Clock();
    camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.set(0, 1.5, 3);
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    document.body.appendChild(renderer.domElement);
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambientLight);
    const directionalLight = new THREE.DirectionalLight(0xffffff, 1);
    directionalLight.position.set(5, 10, 7.5);
    scene.add(directionalLight);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 1, 0);
    controls.update();

    // --- Load Main Avatar ---
    const loader = new GLTFLoader();
    loader.load('assets/avatar.glb', (gltf) => {
        model = gltf.scene;
        scene.add(model);
        mixer = new THREE.AnimationMixer(model);
        // We no longer pre-load the entire dictionary.
        statusElement.textContent = "Click the microphone to start speaking.";
    }, undefined, (error) => {
        console.error("Error loading main avatar:", error);
        statusElement.textContent = "Error: Could not load the main avatar model.";
    });

    // --- Event Listeners ---
    window.addEventListener('resize', onWindowResize);
    micBtn.addEventListener('click', toggleRecording);

    animate();
}

function onWindowResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
}

function animate() {
    requestAnimationFrame(animate);
    const delta = clock.getDelta();
    if (mixer) mixer.update(delta);
    renderer.render(scene, camera);
}

// --- NEW: On-Demand Animation Loader ---
function getAnimationAction(name) {
    return new Promise((resolve, reject) => {
        // 1. Check if the animation is already cached
        if (animationActions[name]) {
            resolve(animationActions[name]);
            return;
        }

        // 2. If not cached, load it from the server
        const path = `assets/${name}.glb`;
        const loader = new GLTFLoader();

        loader.load(path, (gltf) => {
            if (gltf.animations && gltf.animations.length) {
                const action = mixer.clipAction(gltf.animations[0]);
                action.setLoop(THREE.LoopOnce);
                action.clampWhenFinished = true;
                
                // 3. Cache the loaded animation
                animationActions[name] = action;
                console.log(`Successfully loaded and cached animation: ${name}`);
                resolve(action);
            } else {
                reject(`No animation found in ${path}`);
            }
        }, undefined, (error) => {
            console.error(`Failed to load animation ${name}:`, error);
            reject(error);
        });
    });
}

// --- Audio Recording and Processing Logic ---
async function toggleRecording() {
    if (isPlayingAnimation) return;

    if (isRecording) {
        mediaRecorder.stop();
        isRecording = false;
        micBtn.textContent = "Speak";
        micBtn.classList.remove('recording');
        statusElement.textContent = "Processing audio...";
    } else {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            alert('Your browser does not support audio recording.');
            return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];

            mediaRecorder.ondataavailable = event => audioChunks.push(event.data);
            mediaRecorder.onstop = sendAudioToServer;

            mediaRecorder.start();
            isRecording = true;
            micBtn.textContent = "Stop";
            micBtn.classList.add('recording');
            statusElement.textContent = "Listening...";
            transcriptionElement.innerHTML = "&nbsp;";
        } catch (err) {
            console.error("Error accessing microphone:", err);
            statusElement.textContent = "Could not access microphone.";
        }
    }
}

async function sendAudioToServer() {
    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
    const formData = new FormData();
    formData.append('audio_data', audioBlob, 'recording.webm');

    try {
        const response = await fetch('http://127.0.0.1:5000/transcribe', {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) throw new Error(`Server error: ${response.statusText}`);

        const data = await response.json();
        
        transcriptionElement.textContent = `You said: "${data.transcribed_text}"`;
        
        if (data.gloss && data.gloss.length > 0) {
            playAnimationSequence(data.gloss);
        } else {
            statusElement.textContent = "Could not translate the speech. Try again.";
        }

    } catch (error) {
        console.error('Transcription/Translation failed:', error);
        statusElement.textContent = "Failed to process audio.";
    }
}

// --- NEW: More Resilient Animation Sequencer ---
async function playAnimationSequence(sequence) {
    if (isPlayingAnimation) return;

    statusElement.textContent = "Loading required signs...";
    
    // Create a list of promises for the animations to load
    const animationsToLoad = sequence.map(name => getAnimationAction(name));

    // Use Promise.allSettled to wait for all load attempts, even if some fail.
    const results = await Promise.allSettled(animationsToLoad);

    // Log any animations that failed to load for debugging purposes
    results.forEach((result, index) => {
        if (result.status === 'rejected') {
            console.warn(`Could not load animation for "${sequence[index]}". It will be skipped.`);
        }
    });
    
    statusElement.textContent = `Playing sequence: ${sequence.join(' -> ')}`;

    // Now that we've attempted to load everything, start the playback.
    // The playNext function will automatically skip any animations that failed to load.
    animationQueue = [...sequence];
    playNextAnimationInQueue();
}

function playNextAnimationInQueue() {
    if (animationQueue.length === 0) {
        isPlayingAnimation = false;
        statusElement.textContent = "Sequence finished. Click the microphone to speak again.";
        return;
    }

    isPlayingAnimation = true;
    const nextAnimationName = animationQueue.shift();
    const action = animationActions[nextAnimationName]; // Will be undefined if it failed to load

    if (action) {
        action.reset().play();
        const onAnimationFinish = event => {
            if (event.action === action) {
                mixer.removeEventListener('finished', onAnimationFinish);
                playNextAnimationInQueue();
            }
        };
        mixer.addEventListener('finished', onAnimationFinish);
    } else {
        // If the action was not found in our cache, it means it failed to load.
        // We simply skip it and move to the next one in the queue.
        console.warn(`Animation was not found in cache for: ${nextAnimationName}. Skipping.`);
        playNextAnimationInQueue();
    }
}

