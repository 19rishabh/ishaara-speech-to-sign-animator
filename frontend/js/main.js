import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

let scene, camera, renderer, model, mixer, clock;
const animationActions = {}; // Our cache for loaded animations
let currentAction = null; // Keep track of the currently playing action
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

// --- On-Demand Animation Loader ---
function getAnimationAction(name) {
    return new Promise((resolve, reject) => {
        if (animationActions[name]) {
            resolve(animationActions[name]);
            return;
        }
        const path = `assets/${name.toUpperCase()}.glb`;
        const loader = new GLTFLoader();
        loader.load(path, (gltf) => {
            if (gltf.animations && gltf.animations.length) {
                const action = mixer.clipAction(gltf.animations[0]);
                action.setLoop(THREE.LoopOnce);
                action.clampWhenFinished = true;
                animationActions[name] = action;
                resolve(action);
            } else {
                reject(`No animation found in ${path}`);
            }
        }, undefined, () => reject(`Failed to load animation: ${name}`));
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
        const response = await fetch('http://127.0.0.1:5000/transcribe', { method: 'POST', body: formData });
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

// --- UPGRADED: Scalable Animation Sequencer with Blending ---
async function playAnimationSequence(sequence) {
    if (isPlayingAnimation) return;

    statusElement.textContent = "Loading required signs...";
    console.log("Received sequence:", sequence);

    const loadingPromises = sequence.map(name => getAnimationAction(name).catch(e => null));
    const results = await Promise.allSettled(loadingPromises);
    
    animationQueue = [];
    results.forEach((result, index) => {
        if (result.status === 'fulfilled' && result.value) {
            animationQueue.push(sequence[index]);
        } else {
            console.warn(`Animation for "${sequence[index]}" failed to load or does not exist. Skipping.`);
        }
    });

    if (animationQueue.length > 0) {
        statusElement.textContent = `Playing sequence: ${animationQueue.join(' -> ')}`;
        isPlayingAnimation = true;
        playNextAnimationInQueue();
    } else {
        statusElement.textContent = "None of the required signs could be animated. Try again.";
    }
}

function playNextAnimationInQueue() {
    if (animationQueue.length === 0) {
        console.log("Animation queue finished.");
        // Fade out the last action to return to the rest pose
        if(currentAction) {
            const lastAction = currentAction;
            currentAction = null; // Clear current action
            // A short fade out to blend back to the base pose
            setTimeout(() => {
                lastAction.fadeOut(0.5);
            }, (lastAction.getClip().duration - 0.5) * 1000);
        }
        isPlayingAnimation = false;
        statusElement.textContent = "Sequence finished. Click the microphone to speak again.";
        return;
    }

    const nextAnimationName = animationQueue.shift();
    const nextAction = animationActions[nextAnimationName];
    
    console.log(`Playing: ${nextAnimationName}`);

    // If there is no current action, just play the first one
    if (!currentAction) {
        currentAction = nextAction;
        currentAction.reset().play();
    } else {
        const previousAction = currentAction;
        currentAction = nextAction;
        
        // Blend from the previous action to the new one
        previousAction.crossFadeTo(currentAction.reset(), 0.25, true);
        currentAction.play();
    }

    // Use a deterministic timeout to trigger the next animation
    // instead of the 'finished' event listener.
    const animationDuration = currentAction.getClip().duration;
    setTimeout(playNextAnimationInQueue, animationDuration * 1000);
}

