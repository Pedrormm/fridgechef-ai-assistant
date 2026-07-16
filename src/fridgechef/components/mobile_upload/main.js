let componentArgs = {};
let initialized = false;
let processingGeneration = 0;

function setFrameHeight() {
  window.requestAnimationFrame(() => {
    Streamlit.setFrameHeight(Math.max(86, document.documentElement.scrollHeight));
  });
}

function setStatus(message, kind = "info") {
  const status = document.getElementById("upload-status");
  status.textContent = message || "";
  status.dataset.kind = kind;
  setFrameHeight();
}

function setBusy(busy) {
  const button = document.getElementById("select-button");
  button.disabled = busy;
}

function eventId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function supportedFile(file) {
  const mimeType = String(file.type || "").toLowerCase();
  const filename = String(file.name || "").toLowerCase();
  const supportedMimeTypes = new Set(["image/jpeg", "image/jpg", "image/pjpeg", "image/png", "image/webp"]);
  return supportedMimeTypes.has(mimeType) || /\.(jpe?g|png|webp)$/i.test(filename);
}

function canvasToBlob(canvas, quality) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob) {
          resolve(blob);
        } else {
          reject(new Error("The browser could not encode the selected image."));
        }
      },
      "image/jpeg",
      quality,
    );
  });
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(String(reader.result || "")), { once: true });
    reader.addEventListener("error", () => reject(reader.error || new Error("Unable to read the prepared image.")), {
      once: true,
    });
    reader.readAsDataURL(blob);
  });
}

async function loadImageSource(file) {
  if (typeof window.createImageBitmap === "function") {
    try {
      const bitmap = await window.createImageBitmap(file, { imageOrientation: "from-image" });
      return {
        source: bitmap,
        width: bitmap.width,
        height: bitmap.height,
        close: () => bitmap.close(),
      };
    } catch (error) {
      // Some mobile browsers expose createImageBitmap but reject particular
      // gallery providers. The object-URL path below remains widely supported.
    }
  }

  const objectUrl = URL.createObjectURL(file);
  try {
    const image = await new Promise((resolve, reject) => {
      const candidate = new Image();
      candidate.addEventListener("load", () => resolve(candidate), { once: true });
      candidate.addEventListener("error", () => reject(new Error("The selected file is not a readable image.")), {
        once: true,
      });
      candidate.src = objectUrl;
    });
    return {
      source: image,
      width: image.naturalWidth,
      height: image.naturalHeight,
      close: () => URL.revokeObjectURL(objectUrl),
    };
  } catch (error) {
    URL.revokeObjectURL(objectUrl);
    throw error;
  }
}

async function encodeWithinLimit(imageSource, sourceWidth, sourceHeight) {
  const maximumDimension = Math.max(320, Number(componentArgs.maxDimension) || 1920);
  const maximumBytes = Math.max(128 * 1024, Number(componentArgs.maxOutputBytes) || 3 * 1024 * 1024);
  const largestSide = Math.max(sourceWidth, sourceHeight);
  let scale = Math.min(1, maximumDimension / Math.max(1, largestSide));
  const qualities = [0.9, 0.84, 0.76, 0.68, 0.58];
  let lastBlob = null;
  let lastWidth = 0;
  let lastHeight = 0;

  for (let resizeAttempt = 0; resizeAttempt < 5; resizeAttempt += 1) {
    const width = Math.max(1, Math.round(sourceWidth * scale));
    const height = Math.max(1, Math.round(sourceHeight * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d", { alpha: false });
    if (!context) {
      throw new Error("The browser could not prepare an image canvas.");
    }
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, width, height);
    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = "high";
    context.drawImage(imageSource, 0, 0, width, height);

    for (const quality of qualities) {
      const blob = await canvasToBlob(canvas, quality);
      lastBlob = blob;
      lastWidth = width;
      lastHeight = height;
      if (blob.size <= maximumBytes) {
        return { blob: blob, width: width, height: height };
      }
    }
    scale *= 0.78;
  }

  if (lastBlob && lastBlob.size <= maximumBytes * 1.05) {
    return { blob: lastBlob, width: lastWidth, height: lastHeight };
  }
  throw new Error("The prepared image is still too large.");
}

function showLocalPreview(dataUrl) {
  const preview = document.getElementById("local-preview");
  preview.src = dataUrl;
  preview.hidden = false;
  setFrameHeight();
}

function clearLocalPreview() {
  const preview = document.getElementById("local-preview");
  preview.removeAttribute("src");
  preview.hidden = true;
  setFrameHeight();
}

function emitFailure(file, message) {
  const failureId = eventId();
  setStatus(message, "error");
  Streamlit.setComponentValue({
    eventId: failureId,
    uploadId: failureId,
    filename: file ? String(file.name || "foto") : "foto",
    originalSize: file ? Number(file.size || 0) : 0,
    error: message,
  });
}

async function prepareSelectedFile(file) {
  if (!file) {
    return;
  }

  const generation = ++processingGeneration;
  clearLocalPreview();
  setBusy(true);
  setStatus(componentArgs.processingLabel || "Preparando la foto…");

  try {
    const maximumSourceBytes = Math.max(1, Number(componentArgs.maxSourceBytes) || 25 * 1024 * 1024);
    if (file.size > maximumSourceBytes) {
      emitFailure(file, componentArgs.tooLargeLabel || "La foto es demasiado grande para prepararla.");
      return;
    }
    if (!supportedFile(file)) {
      emitFailure(file, componentArgs.unsupportedLabel || "Este formato no es compatible. Usa JPG, PNG o WEBP.");
      return;
    }

    const loaded = await loadImageSource(file);
    try {
      if (!loaded.width || !loaded.height) {
        throw new Error("The selected image has invalid dimensions.");
      }
      const prepared = await encodeWithinLimit(loaded.source, loaded.width, loaded.height);
      const dataUrl = await blobToDataUrl(prepared.blob);
      if (generation !== processingGeneration) {
        return;
      }

      const uploadId = eventId();
      showLocalPreview(dataUrl);
      setStatus(componentArgs.readyLabel || "Foto preparada. Ya puedes analizarla.", "success");
      Streamlit.setComponentValue({
        dataUrl: dataUrl,
        uploadId: uploadId,
        filename: String(file.name || "foto.jpg"),
        mimeType: "image/jpeg",
        originalMimeType: String(file.type || ""),
        originalSize: Number(file.size || 0),
        processedSize: Number(prepared.blob.size || 0),
        width: prepared.width,
        height: prepared.height,
      });
    } finally {
      loaded.close();
    }
  } catch (error) {
    console.error("Unable to prepare the selected mobile image", error);
    emitFailure(file, componentArgs.failedLabel || "No he podido preparar esta foto. Prueba con otra imagen.");
  } finally {
    if (generation === processingGeneration) {
      setBusy(false);
    }
  }
}

function initialize(args) {
  componentArgs = Object.assign(componentArgs, args || {});
  const input = document.getElementById("gallery-input");
  const button = document.getElementById("select-button");
  input.accept = componentArgs.accept || ".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp";
  button.textContent = componentArgs.selectLabel || "Seleccionar foto";

  if (initialized) {
    setFrameHeight();
    return;
  }
  initialized = true;

  button.addEventListener("click", () => {
    // Resetting the native value lets users select the same gallery file twice.
    input.value = "";
    input.click();
  });
  input.addEventListener("change", () => {
    const file = input.files && input.files.length ? input.files[0] : null;
    prepareSelectedFile(file);
  });
  window.addEventListener("resize", setFrameHeight);
  setFrameHeight();
}

Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, (event) => {
  initialize(event.detail.args || {});
});
Streamlit.setComponentReady();
