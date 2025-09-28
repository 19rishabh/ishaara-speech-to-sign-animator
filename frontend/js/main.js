// Import necessary modules from the Three.js library
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// --- Core Three.js Components ---
let scene, camera, renderer, clock, mixer;
let model; // This will hold our loaded avatar
const animationActions = {}; // An object to store our animations

// --- Initialization ---
init();

function init() {
    // 1. Scene: The container for all our 3D objects
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0xeeeeee);

    // 2. Clock: Essential for animation updates
    clock = new THREE.Clock();

    // 3. Renderer: Draws the scene onto the canvas
    const canvas = document.getElementById('avatar-canvas');
    renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.shadowMap.enabled = true; // Enable shadows

    // 4. Camera: Our viewpoint into the scene
    camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.set(0, 1.5, 3); // Position the camera

    // 5. Lighting: To make the model visible
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
    scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 1);
    directionalLight.position.set(5, 10, 7.5);
    directionalLight.castShadow = true;
    scene.add(directionalLight);

    // 6. Controls: To let the user interact with the scene
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 1, 0); // Set the point to orbit around
    controls.update();

    // --- Load Models & Animations ---
    const loader = new GLTFLoader();

    // Load the main avatar model
    loader.load('assets/avatar.glb', (gltf) => {
        model = gltf.scene;
        model.position.y = 0; // Position model at the base
        scene.add(model);
        
        // Setup the animation mixer
        mixer = new THREE.AnimationMixer(model);

        // Load our test animation
        loadAnimation('hello', 'assets/hello.glb');

        // Start the animation loop once the model is loaded
        animate(); 
    }, undefined, (error) => {
        console.error('An error happened while loading the model:', error);
    });

    // --- Event Listeners ---
    document.getElementById('hello-btn').addEventListener('click', () => playAnimation('hello'));
    window.addEventListener('resize', onWindowResize);
}

function loadAnimation(name, path) {
    const loader = new GLTFLoader();
    loader.load(path, (gltf) => {
        // Check if the loaded file actually contains animations
        if (gltf.animations && gltf.animations.length) {
            const action = mixer.clipAction(gltf.animations[0]);
            action.setLoop(THREE.LoopOnce); // We don't want it to loop
            action.clampWhenFinished = true; // Stay on the last frame
            animationActions[name] = action;
            console.log(`Animation '${name}' loaded successfully.`);
        } else {
            // Log a more helpful error if no animations are found
            console.error(`Error: The file at ${path} does not contain any animations. Check your Blender export settings.`);
        }
    });
}

function playAnimation(name) {
    if (animationActions[name]) {
        // Reset and play the requested animation
        mixer.stopAllAction(); // Stop any other playing animations
        animationActions[name].reset().play();
    }
}

// --- Core Animation Loop ---
function animate() {
    requestAnimationFrame(animate);

    // Update the animation mixer
    if (mixer) {
        mixer.update(clock.getDelta());
    }

    renderer.render(scene, camera);
}

// --- Utility Functions ---
function onWindowResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
}

