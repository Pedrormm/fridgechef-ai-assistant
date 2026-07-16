let activeStream = null;
let activeFacingMode = "environment";
let componentArgs = {};
let initialized = false;

function setFrameHeight() {
  window.requestAnimationFrame(() => {
    Streamlit.setFrameHeight(Math.max(260, document.documentElement.scrollHeight));
  });
}

function setStatus(message, kind = "info") {
  const status = document.getElementById("camera-status");
  status.textContent = message;
  status.dataset.kind = kind;
  setFrameHeight();
}

function stopActiveStream() {
  if (!activeStream) {
    return;
  }
  activeStream.getTracks().forEach((track) => track.stop());
  activeStream = null;
}

function cameraConstraints(facingMode, exact) {
  const facingConstraint = exact ? { exact: facingMode } : { ideal: facingMode };
  return {
    audio: false,
    video: {
      facingMode: facingConstraint,
      width: { ideal: 1920 },
      height: { ideal: 1080 },
    },
  };
}

async function requestCamera(facingMode) {
  const attempts = [
    cameraConstraints(facingMode, true),
    cameraConstraints(facingMode, false),
    { audio: false, video: true },
  ];

  let lastError = null;
  for (const constraints of attempts) {
    try {
      return await navigator.mediaDevices.getUserMedia(constraints);
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error("No camera is available.");
}

function cameraErrorMessage(error) {
  const name = error && error.name ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "No se ha permitido usar la cámara. Revisa los permisos del navegador y vuelve a intentarlo.";
  }
  if (name === "NotFoundError" || name === "OverconstrainedError") {
    return "No he encontrado una cámara compatible en este dispositivo.";
  }
  if (name === "NotReadableError" || name === "AbortError") {
    return "La cámara está siendo utilizada por otra aplicación. Ciérrala y vuelve a intentarlo.";
  }
  return "No he podido abrir la cámara. Puedes usar la pestaña Subir foto como alternativa.";
}

async function startCamera(facingMode) {
  const video = document.getElementById("camera-preview");
  const captureButton = document.getElementById("capture-button");
  captureButton.disabled = true;
  stopActiveStream();
  setStatus(
    facingMode === "environment"
      ? componentArgs.startingLabel || "Abriendo la cámara trasera…"
      : "Abriendo la cámara frontal…",
  );

  try {
    const stream = await requestCamera(facingMode);
    activeStream = stream;
    video.srcObject = stream;
    await video.play();

    const track = stream.getVideoTracks()[0];
    const settings = track && track.getSettings ? track.getSettings() : {};
    activeFacingMode = settings.facingMode || facingMode;
    video.classList.toggle("mirror", activeFacingMode === "user");
    captureButton.disabled = false;
    setStatus(
      activeFacingMode === "environment"
        ? "Cámara trasera preparada."
        : "Cámara frontal preparada. Usa Cambiar cámara para intentar abrir la trasera.",
      "success",
    );
  } catch (error) {
    console.error("Unable to start the device camera", error);
    setStatus(cameraErrorMessage(error), "error");
  }
}

function capturePhoto() {
  const video = document.getElementById("camera-preview");
  const canvas = document.getElementById("camera-canvas");
  if (!activeStream || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
    setStatus("Espera a que la cámara termine de prepararse.", "error");
    return;
  }

  const sourceWidth = video.videoWidth || 1280;
  const sourceHeight = video.videoHeight || 720;
  const maximumWidth = 1920;
  const scale = Math.min(1, maximumWidth / sourceWidth);
  const width = Math.max(1, Math.round(sourceWidth * scale));
  const height = Math.max(1, Math.round(sourceHeight * scale));

  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { alpha: false });
  context.drawImage(video, 0, 0, width, height);

  const dataUrl = canvas.toDataURL("image/jpeg", 0.9);
  Streamlit.setComponentValue({
    dataUrl: dataUrl,
    captureId: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    width: width,
    height: height,
    facingMode: activeFacingMode,
  });
  setStatus("Foto realizada. Ya puedes analizarla.", "success");
}

async function switchCamera() {
  const nextFacingMode = activeFacingMode === "environment" ? "user" : "environment";
  await startCamera(nextFacingMode);
}

function initialize(args) {
  if (initialized) {
    componentArgs = Object.assign(componentArgs, args || {});
    return;
  }
  initialized = true;
  componentArgs = args || {};

  const captureButton = document.getElementById("capture-button");
  const switchButton = document.getElementById("switch-button");
  captureButton.textContent = componentArgs.captureLabel || "Hacer foto";
  switchButton.textContent = componentArgs.switchLabel || "Cambiar cámara";
  captureButton.addEventListener("click", capturePhoto);
  switchButton.addEventListener("click", switchCamera);

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setStatus("Este navegador no permite acceder a la cámara. Usa la pestaña Subir foto.", "error");
    switchButton.disabled = true;
    return;
  }

  const preferredFacingMode = componentArgs.preferredFacingMode === "user" ? "user" : "environment";
  startCamera(preferredFacingMode);
  window.addEventListener("pagehide", stopActiveStream);
  window.addEventListener("beforeunload", stopActiveStream);
  window.addEventListener("resize", setFrameHeight);
  setFrameHeight();
}

Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, (event) => {
  initialize(event.detail.args || {});
});
Streamlit.setComponentReady();
