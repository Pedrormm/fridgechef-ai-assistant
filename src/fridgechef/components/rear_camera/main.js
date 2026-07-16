let activeStream = null;
let activeFacingMode = "environment";
let desiredFacingMode = "environment";
let componentArgs = {};
let initialized = false;
let cameraStarting = false;
let startGeneration = 0;
let visibilityTimer = null;

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

function previewElement() {
  return document.getElementById("camera-preview");
}

function stopActiveStream() {
  const video = previewElement();
  if (video) {
    video.pause();
    video.srcObject = null;
  }
  if (activeStream) {
    activeStream.getTracks().forEach((track) => track.stop());
    activeStream = null;
  }
}

function isComponentVisible() {
  if (document.visibilityState === "hidden") {
    return false;
  }

  const shell = document.querySelector(".camera-shell");
  const shellRect = shell ? shell.getBoundingClientRect() : null;
  if (!shellRect || shellRect.width < 2 || shellRect.height < 2) {
    return false;
  }

  try {
    const frame = window.frameElement;
    if (frame) {
      const frameRect = frame.getBoundingClientRect();
      const frameStyle = window.parent.getComputedStyle(frame);
      if (
        frameRect.width < 2 ||
        frameRect.height < 2 ||
        frameStyle.display === "none" ||
        frameStyle.visibility === "hidden"
      ) {
        return false;
      }
    }
  } catch (error) {
    // Sandboxed browsers can block access to the parent frame. The local shell
    // dimensions still provide a safe fallback in that case.
  }

  return true;
}

function cameraConstraints(facingMode, exact) {
  const facingConstraint = exact ? { exact: facingMode } : { ideal: facingMode };
  return {
    audio: false,
    video: {
      facingMode: facingConstraint,
      width: { ideal: 1280 },
      height: { ideal: 720 },
      frameRate: { ideal: 30 },
    },
  };
}

async function requestCamera(facingMode) {
  const attempts = [
    cameraConstraints(facingMode, false),
    cameraConstraints(facingMode, true),
    { audio: false, video: { facingMode: { ideal: facingMode } } },
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

function waitForMetadata(video, timeoutMs = 5000) {
  if (video.readyState >= HTMLMediaElement.HAVE_METADATA && video.videoWidth > 0) {
    return Promise.resolve();
  }

  return new Promise((resolve, reject) => {
    let finished = false;
    const cleanup = () => {
      video.removeEventListener("loadedmetadata", onReady);
      video.removeEventListener("loadeddata", onReady);
      window.clearTimeout(timer);
    };
    const onReady = () => {
      if (finished || video.videoWidth <= 0 || video.videoHeight <= 0) {
        return;
      }
      finished = true;
      cleanup();
      resolve();
    };
    const timer = window.setTimeout(() => {
      if (finished) {
        return;
      }
      finished = true;
      cleanup();
      reject(new Error("Camera metadata did not become available."));
    }, timeoutMs);
    video.addEventListener("loadedmetadata", onReady);
    video.addEventListener("loadeddata", onReady);
  });
}

function waitForLiveFrames(video, timeoutMs = 4500) {
  return new Promise((resolve, reject) => {
    let finished = false;
    let frameCount = 0;
    const startedAt = video.currentTime;
    let interval = null;

    const finish = (error) => {
      if (finished) {
        return;
      }
      finished = true;
      if (interval !== null) {
        window.clearInterval(interval);
      }
      window.clearTimeout(timer);
      if (error) {
        reject(error);
      } else {
        resolve();
      }
    };

    const timer = window.setTimeout(() => {
      finish(new Error("The camera preview did not produce live frames."));
    }, timeoutMs);

    if (typeof video.requestVideoFrameCallback === "function") {
      const onFrame = () => {
        frameCount += 1;
        if (frameCount >= 2) {
          finish();
          return;
        }
        video.requestVideoFrameCallback(onFrame);
      };
      video.requestVideoFrameCallback(onFrame);
      return;
    }

    interval = window.setInterval(() => {
      if (
        video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA &&
        video.currentTime > startedAt + 0.02
      ) {
        finish();
      }
    }, 100);
  });
}

function delay(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function startCamera(facingMode, retryCount = 0) {
  if (!isComponentVisible()) {
    desiredFacingMode = facingMode;
    setStatus("Abre esta pestaña para preparar la cámara.");
    return;
  }

  const generation = ++startGeneration;
  const video = previewElement();
  const captureButton = document.getElementById("capture-button");
  const switchButton = document.getElementById("switch-button");
  desiredFacingMode = facingMode;
  cameraStarting = true;
  captureButton.disabled = true;
  switchButton.disabled = true;
  stopActiveStream();
  setStatus(
    facingMode === "environment"
      ? componentArgs.startingLabel || "Abriendo la cámara trasera…"
      : "Abriendo la cámara frontal…",
  );

  try {
    const stream = await requestCamera(facingMode);
    if (generation !== startGeneration || !isComponentVisible()) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }

    activeStream = stream;
    video.srcObject = stream;
    await waitForMetadata(video);
    await video.play();
    await waitForLiveFrames(video);

    if (generation !== startGeneration) {
      return;
    }

    const track = stream.getVideoTracks()[0];
    const settings = track && track.getSettings ? track.getSettings() : {};
    activeFacingMode = settings.facingMode || facingMode;
    desiredFacingMode = activeFacingMode;
    video.classList.toggle("mirror", activeFacingMode === "user");
    captureButton.disabled = false;
    switchButton.disabled = false;
    setStatus(
      activeFacingMode === "environment"
        ? "Cámara trasera preparada."
        : "Cámara frontal preparada. Usa Cambiar cámara para intentar abrir la trasera.",
      "success",
    );
  } catch (error) {
    stopActiveStream();
    if (retryCount < 1 && isComponentVisible()) {
      await delay(250);
      cameraStarting = false;
      await startCamera(facingMode, retryCount + 1);
      return;
    }
    console.error("Unable to start the device camera", error);
    captureButton.disabled = true;
    switchButton.disabled = false;
    setStatus(cameraErrorMessage(error), "error");
  } finally {
    if (generation === startGeneration) {
      cameraStarting = false;
    }
  }
}

function capturePhoto() {
  const video = previewElement();
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

function monitorVisibility() {
  if (visibilityTimer !== null) {
    return;
  }
  visibilityTimer = window.setInterval(() => {
    const visible = isComponentVisible();
    if (!visible && activeStream) {
      ++startGeneration;
      stopActiveStream();
      cameraStarting = false;
      setStatus("Abre esta pestaña para preparar la cámara.");
      return;
    }
    if (visible && !activeStream && !cameraStarting) {
      startCamera(desiredFacingMode);
    }
  }, 250);
}

function initialize(args) {
  componentArgs = Object.assign(componentArgs, args || {});
  if (initialized) {
    setFrameHeight();
    return;
  }
  initialized = true;

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

  desiredFacingMode = componentArgs.preferredFacingMode === "user" ? "user" : "environment";
  monitorVisibility();
  if (isComponentVisible()) {
    startCamera(desiredFacingMode);
  } else {
    setStatus("Abre esta pestaña para preparar la cámara.");
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && isComponentVisible() && !activeStream) {
      startCamera(desiredFacingMode);
    }
  });
  window.addEventListener("pageshow", () => {
    if (isComponentVisible() && !activeStream) {
      startCamera(desiredFacingMode);
    }
  });
  window.addEventListener("pagehide", stopActiveStream);
  window.addEventListener("beforeunload", stopActiveStream);
  window.addEventListener("resize", setFrameHeight);
  setFrameHeight();
}

Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, (event) => {
  initialize(event.detail.args || {});
});
Streamlit.setComponentReady();
