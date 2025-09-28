import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

let scene, camera, renderer, model, mixer, clock;
const animationActions = {};
let animationQueue = []; // A queue to hold the sequence of animations to play
let isPlayingAnimation = false;

// --- DOM ELEMENTS ---
const statusElement = document.getElementById('status');
const textInput = document.getElementById('text-input');
const translateBtn = document.getElementById('translate-btn');

init();

function init() {
    // --- Basic Scene Setup ---
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0xeeeeee);
    clock = new THREE.Clock();

    // --- Camera ---
    camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.set(0, 1.5, 3);

    // --- Renderer ---
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    document.body.appendChild(renderer.domElement);

    // --- Lighting ---
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambientLight);
    const directionalLight = new THREE.DirectionalLight(0xffffff, 1);
    directionalLight.position.set(5, 10, 7.5);
    scene.add(directionalLight);

    // --- Controls ---
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 1, 0);
    controls.update();

    // --- Load Main Avatar ---
    const loader = new GLTFLoader();
    loader.load('assets/avatar.glb', (gltf) => {
        model = gltf.scene;
        model.position.set(0, 0, 0);
        scene.add(model);
        
        // Setup the animation mixer
        mixer = new THREE.AnimationMixer(model);
        
        // --- PRE-LOAD ANIMATIONS ---
        // For a real project, you would load all animations you have.
        // The key of the object (e.g., 'HELLO') should match the gloss word.
        loadAnimation('HELLO', 'assets/hello.glb');
        // TODO: Add more loadAnimation calls for each .glb file you create
        // loadAnimation('I', 'assets/i.glb');
        // loadAnimation('NAME', 'assets/name.glb');

        statusElement.textContent = "Ready. Enter a sentence.";
    });

    // --- Event Listeners ---
    window.addEventListener('resize', onWindowResize);
    translateBtn.addEventListener('click', onTranslateClick);

    // Start the animation loop
    animate();
}

function onWindowResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
}

function loadAnimation(name, path) {
    const loader = new GLTFLoader();
    loader.load(path, (gltf) => {
        if (gltf.animations && gltf.animations.length) {
            const action = mixer.clipAction(gltf.animations[0]);
            action.setLoop(THREE.LoopOnce);
            action.clampWhenFinished = true;
            animationActions[name.toUpperCase()] = action; // Use uppercase to match gloss
            console.log(`Animation '${name}' loaded successfully.`);
        } else {
            console.error(`Error: The file at ${path} does not contain any animations.`);
        }
    }, undefined, (error) => {
        console.error(`An error happened loading animation: ${name}`, error);
    });
}

function animate() {
    requestAnimationFrame(animate);
    const delta = clock.getDelta();
    if (mixer) {
        mixer.update(delta);
    }
    renderer.render(scene, camera);
}

// --- NEW: Handle Translation Request ---
async function onTranslateClick() {
    const text = textInput.value;
    if (!text) {
        statusElement.textContent = "Please enter some text.";
        return;
    }

    statusElement.textContent = "Translating...";
    
    try {
        // Send the text to our Flask backend
        const response = await fetch('http://127.0.0.1:5000/translate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ text: text }),
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.statusText}`);
        }

        const data = await response.json();
        const glossSequence = data.gloss;
        
        if (glossSequence && glossSequence.length > 0) {
            statusElement.textContent = `Playing sequence: ${glossSequence.join(' -> ')}`;
            playAnimationSequence(glossSequence);
        } else {
            statusElement.textContent = "Could not translate the text.";
        }

    } catch (error) {
        console.error('Translation failed:', error);
        statusElement.textContent = "Failed to connect to the translation server.";
    }
}

// --- NEW: Animation Sequencer ---
function playAnimationSequence(sequence) {
    animationQueue = [...sequence]; // Copy the sequence to our queue
    
    // If an animation is not already playing, start the sequence
    if (!isPlayingAnimation) {
        playNextAnimationInQueue();
    }
}

function playNextAnimationInQueue() {
    if (animationQueue.length === 0) {
        isPlayingAnimation = false;
        statusElement.textContent = "Sequence finished. Ready for next input.";
        return;
    }

    isPlayingAnimation = true;
    const nextAnimationName = animationQueue.shift(); // Get the next animation name
    const action = animationActions[nextAnimationName];

    if (action) {
        // Reset and play the action
        action.reset().play();
        
        // Listen for when the animation finishes
        const onAnimationFinish = (event) => {
            if (event.action === action) {
                mixer.removeEventListener('finished', onAnimationFinish);
                playNextAnimationInQueue(); // Play the next one
            }
        };
        mixer.addEventListener('finished', onAnimationFinish);

    } else {
        console.warn(`Animation not found for: ${nextAnimationName}. Skipping.`);
        playNextAnimationInQueue(); // Skip to the next one
    }
}

