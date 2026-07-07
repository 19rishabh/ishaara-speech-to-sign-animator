import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

let scene, camera, renderer, model, mixer, clock, controls, gridHelper; // NEW: gridHelper is now global
const animationActions = {}; 
let currentAction = null; 
let animationQueue = [];
let isPlayingAnimation = false;

// --- Audio Recording Variables ---
let mediaRecorder;
let audioChunks = [];
let isRecording = false;

// --- DOM ELEMENTS ---
const statusElement = document.getElementById('status');
const textInput = document.getElementById('text-input'); 
const micBtn = document.getElementById('mic-btn');
const micBtnText = document.getElementById('mic-btn-text'); 
const translateBtn = document.getElementById('translate-btn'); 
const canvasContainer = document.getElementById('canvas-container');
// --- NEW: Theme Toggle Elements ---
const themeToggleBtn = document.getElementById('theme-toggle');
const sunIcon = document.getElementById('sun-icon');
const moonIcon = document.getElementById('moon-icon');

// --- NEW: Theme Colors ---
const lightTheme = {
    bg: 0xf0f4f8,
    grid: 0xcccccc,
    fog: 0xf0f4f8
};
const darkTheme = {
    bg: 0x18181b, // zinc-900
    grid: 0x3f3f46, // zinc-700
    fog: 0x18181b
};

init();

function init() {
    // --- Basic Scene Setup ---
    scene = new THREE.Scene();
    scene.background = new THREE.Color(lightTheme.bg); 
    scene.fog = new THREE.Fog(lightTheme.fog, 10, 25); 
    clock = new THREE.Clock();
    camera = new THREE.PerspectiveCamera(75, canvasContainer.clientWidth / canvasContainer.clientHeight, 0.1, 1000);
    camera.position.set(0, 1.5, 2);
    
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(canvasContainer.clientWidth, canvasContainer.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    canvasContainer.appendChild(renderer.domElement); 

    // --- Enhanced Lighting ---
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.7); 
    scene.add(ambientLight);
    const directionalLight = new THREE.DirectionalLight(0xffffff, 1.2);
    directionalLight.position.set(5, 10, 7.5);
    scene.add(directionalLight);
    const hemiLight = new THREE.HemisphereLight( 0xffffff, 0x444444, 0.6 );
    hemiLight.position.set( 0, 20, 0 );
    scene.add( hemiLight );

    // --- Add Floor Grid ---
    gridHelper = new THREE.GridHelper(10, 10, lightTheme.grid, lightTheme.grid); // Use theme color
    scene.add(gridHelper);
    
    // --- Add OrbitControls for camera interaction ---
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true; 
    controls.dampingFactor = 0.05;
    controls.screenSpacePanning = false;
    controls.minDistance = 1.5; 
    controls.maxDistance = 10; 
    controls.target.set(0, 1.2, 0); 
    controls.update();

    // --- Load Main Avatar ---
    const loader = new GLTFLoader();
    loader.load('assets/avatar.glb', (gltf) => { 
        model = gltf.scene;
        scene.add(model);
        mixer = new THREE.AnimationMixer(model);
        statusElement.textContent = "Ready.";
    }, 
    undefined, 
    (error) => {
        console.error("CRITICAL: FAILED TO LOAD AVATAR MODEL.", error);
        statusElement.textContent = "Error: Avatar model not found in /assets/avatar.glb";
        statusElement.classList.add('text-red-500', 'font-bold');
        micBtn.disabled = true;
        translateBtn.disabled = true;
    });

    // --- Event Listeners ---
    window.addEventListener('resize', onWindowResize);
    micBtn.addEventListener('click', toggleRecording);
    translateBtn.addEventListener('click', sendTextToTranslate);
    
    // --- NEW: Theme Toggle Listener ---
    themeToggleBtn.addEventListener('click', toggleTheme);
    
    // --- NEW: Enable/disable translate button based on text input ---
    textInput.addEventListener('input', () => {
        translateBtn.disabled = textInput.value.trim() === '';
    });
    translateBtn.disabled = true; // Disabled by default

    // --- NEW: Set initial theme on load ---
    const currentTheme = localStorage.theme || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    setTheme(currentTheme);

    animate();
}

// --- NEW: Theme Control Functions ---
function setTheme(mode) {
    if (mode === 'dark') {
        document.documentElement.classList.add('dark');
        localStorage.theme = 'dark';
        sunIcon.classList.add('hidden');
        moonIcon.classList.remove('hidden');
        
        // Update 3D scene colors
        if (scene) {
            scene.background.set(darkTheme.bg);
            scene.fog.color.set(darkTheme.fog);
            gridHelper.material.color.set(darkTheme.grid);
        }
    } else {
        document.documentElement.classList.remove('dark');
        localStorage.theme = 'light';
        sunIcon.classList.remove('hidden');
        moonIcon.classList.add('hidden');
        
        // Update 3D scene colors
        if (scene) {
            scene.background.set(lightTheme.bg);
            scene.fog.color.set(lightTheme.fog);
            gridHelper.material.color.set(lightTheme.grid);
        }
    }
}

function toggleTheme() {
    const currentMode = document.documentElement.classList.contains('dark') ? 'dark' : 'light';
    const newMode = currentMode === 'dark' ? 'light' : 'dark';
    setTheme(newMode);
}
// --- End of Theme Control Functions ---

function onWindowResize() {
    camera.aspect = canvasContainer.clientWidth / canvasContainer.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(canvasContainer.clientWidth, canvasContainer.clientHeight);
}

function animate() {
    requestAnimationFrame(animate);
    const delta = clock.getDelta();
    if (mixer) mixer.update(delta);
    if (controls) controls.update();
    renderer.render(scene, camera);
}

// --- On-Demand Animation Loader ---
// Resolves with the key under which the loaded action is cached in animationActions,
// so callers (the animation queue) don't need to hold onto the action objects directly.
function getAnimationAction(name) {
    return new Promise((resolve, reject) => {
        if (!mixer) {
            reject("Mixer not initialized. Cannot load animation.");
            return;
        }
        if (animationActions[name]) {
            resolve(name);
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
                resolve(name);
            } else {
                reject(`No animation found in ${path}`);
            }
        }, undefined, () => reject(`Failed to load animation: ${name}`));
    });
}

// --- Fingerspelling Fallback Loader ---
// Used for out-of-vocabulary gloss words (e.g. proper names) that have no whole-word
// sign. Loads per-letter handshape clips from assets/fingerspell/. Cached under an
// "FS_" prefix so a letter like "I" never collides with the whole-word sign "I.glb".
function getFingerspellAction(letter) {
    return new Promise((resolve, reject) => {
        if (!mixer) {
            reject("Mixer not initialized. Cannot load animation.");
            return;
        }
        const upperLetter = letter.toUpperCase();
        const key = `FS_${upperLetter}`;
        if (animationActions[key]) {
            resolve(key);
            return;
        }
        const path = `assets/fingerspell/${upperLetter}.glb`;
        const loader = new GLTFLoader();
        loader.load(path, (gltf) => {
            if (gltf.animations && gltf.animations.length) {
                const action = mixer.clipAction(gltf.animations[0]);
                action.setLoop(THREE.LoopOnce);
                action.clampWhenFinished = true;
                animationActions[key] = action;
                resolve(key);
            } else {
                reject(`No fingerspelling animation found in ${path}`);
            }
        }, undefined, () => reject(`Failed to load fingerspelling animation: ${letter}`));
    });
}

// --- MODIFIED: Audio Recording Logic ---
async function toggleRecording() {
    if (isPlayingAnimation) return;
    if (isRecording) {
        // --- STOP RECORDING ---
        mediaRecorder.stop();
        isRecording = false;
        
        micBtn.classList.remove('recording', 'bg-red-500', 'hover:bg-red-600');
        micBtn.classList.add('bg-green-500', 'hover:bg-green-600');
        micBtnText.textContent = "Record";
        statusElement.textContent = "Transcribing audio...";
        translateBtn.disabled = true;
    } else {
        // --- START RECORDING ---
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];
            mediaRecorder.ondataavailable = event => audioChunks.push(event.data);
            mediaRecorder.onstop = sendAudioToServer; // This function is now different
            
            mediaRecorder.start();
            isRecording = true;
            
            micBtn.classList.remove('bg-green-500', 'hover:bg-green-600');
            micBtn.classList.add('recording', 'bg-red-500', 'hover:bg-red-600');
            micBtnText.textContent = "Stop";
            statusElement.textContent = "Listening...";
            textInput.value = ""; // Clear text input
            translateBtn.disabled = true;
        } catch (err) {
            console.error("Error accessing microphone:", err);
            statusElement.textContent = "Could not access microphone.";
        }
    }
}

// --- MODIFIED: This function now ONLY transcribes and populates the text area ---
async function sendAudioToServer() {
    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
    const formData = new FormData();
    formData.append('audio_data', audioBlob, 'recording.webm');
    try {
        const response = await fetch('http://127.0.0.1:5000/transcribe', { method: 'POST', body: formData });
        if (!response.ok) throw new Error(`Server error: ${response.statusText}`);
        
        const data = await response.json();
        
        // Populate the text area with the transcribed text
        textInput.value = data.transcribed_text || ""; 
        statusElement.textContent = "Transcription complete. Edit or click 'Translate'.";
        
        // Enable the translate button
        translateBtn.disabled = textInput.value.trim() === '';

    } catch (error) {
        console.error('Transcription failed:', error);
        statusElement.textContent = "Failed to transcribe audio.";
        translateBtn.disabled = true;
    }
}

// --- NEW: This function handles the translation and animation ---
async function sendTextToTranslate() {
    if (isPlayingAnimation) return;
    
    const text = textInput.value;
    if (!text.trim()) {
        statusElement.textContent = "Nothing to translate.";
        return;
    }

    statusElement.textContent = "Translating text...";
    translateBtn.disabled = true;
    micBtn.disabled = true;

    try {
        const response = await fetch('http://127.0.0.1:5000/translate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text })
        });
        
        if (!response.ok) throw new Error(`Server error: ${response.statusText}`);

        const data = await response.json();
        
        if (data.gloss && data.gloss.length > 0) {
            playAnimationSequence(data.gloss);
        } else {
            statusElement.textContent = "Could not translate the text.";
            translateBtn.disabled = false;
            micBtn.disabled = false;
        }
    } catch (error) {
        console.error('Translation failed:', error);
        statusElement.textContent = "Failed to translate text.";
        translateBtn.disabled = false;
        micBtn.disabled = false;
    }
}

// --- UPGRADED: Scalable Animation Sequencer with Blending + Fingerspelling Fallback ---
async function playAnimationSequence(sequence) {
    statusElement.textContent = "Loading required signs...";
    console.log("Received sequence:", sequence);

    const loadingPromises = sequence.map(name => getAnimationAction(name).catch(() => null));
    const results = await Promise.allSettled(loadingPromises);

    animationQueue = [];
    for (let i = 0; i < results.length; i++) {
        const result = results[i];
        const word = sequence[i];

        if (result.status === 'fulfilled' && result.value) {
            animationQueue.push(result.value);
            continue;
        }

        // No whole-word sign for this gloss token - try fingerspelling it letter by letter.
        const letters = word.replace(/[^A-Za-z]/g, '').split('');
        if (letters.length === 0) {
            console.warn(`Animation for "${word}" failed to load or does not exist. Skipping.`);
            continue;
        }

        const letterKeys = [];
        let allLettersLoaded = true;
        for (const letter of letters) {
            try {
                letterKeys.push(await getFingerspellAction(letter));
            } catch (e) {
                allLettersLoaded = false;
                break;
            }
        }

        if (allLettersLoaded) {
            console.warn(`No whole-word sign for "${word}" - using fingerspelling fallback.`);
            animationQueue.push(...letterKeys);
        } else {
            console.warn(`No sign or fingerspelling available for "${word}". Skipping.`);
        }
    }

    if (animationQueue.length > 0) {
        statusElement.textContent = `Playing sequence: ${animationQueue.join(' -> ')}`;
        isPlayingAnimation = true;
        playNextAnimationInQueue();
    } else {
        statusElement.textContent = "Signs translated, but no animations found. Try 'hello'.";
        translateBtn.disabled = false;
        micBtn.disabled = false;
    }
}

function playNextAnimationInQueue() {
    if (animationQueue.length === 0) {
        console.log("Animation queue finished.");
        if(currentAction) {
            const lastAction = currentAction;
            currentAction = null; 
            const fadeOutTime = 0.5; 
            const clipDuration = lastAction.getClip().duration;
            const waitTime = (clipDuration - fadeOutTime) * 1000;
            
            if (waitTime > 0) {
                 setTimeout(() => { lastAction.fadeOut(fadeOutTime); }, waitTime);
            } else {
                lastAction.fadeOut(0.1); 
            }
        }
        isPlayingAnimation = false;
        statusElement.textContent = "Sequence finished. Ready.";
        translateBtn.disabled = false;
        micBtn.disabled = false;
        return;
    }

    const nextAnimationName = animationQueue.shift();
    const nextAction = animationActions[nextAnimationName];
    
    console.log(`Playing: ${nextAnimationName}`);

    if (!currentAction) {
        currentAction = nextAction;
        currentAction.reset().play();
    } else {
        const previousAction = currentAction;
        currentAction = nextAction;
        
        const blendDuration = 0.25; 
        previousAction.crossFadeTo(currentAction.reset(), blendDuration, true);
        currentAction.play();
    }

    const animationDuration = currentAction.getClip().duration;
    const nextTriggerTime = (animationDuration - 0.25) * 1000;
    setTimeout(playNextAnimationInQueue, nextTriggerTime > 0 ? nextTriggerTime : animationDuration * 1000);
}