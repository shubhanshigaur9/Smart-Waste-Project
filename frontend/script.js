(() => {
  const menuButton = document.querySelector(".menu-toggle");
  const navigation = document.querySelector(".nav-links");

  if (menuButton && navigation) {
    menuButton.addEventListener("click", () => {
      const isOpen = menuButton.getAttribute("aria-expanded") === "true";
      menuButton.setAttribute("aria-expanded", String(!isOpen));
      menuButton.setAttribute("aria-label", isOpen ? "Open navigation menu" : "Close navigation menu");
      navigation.classList.toggle("is-open", !isOpen);
    });
    navigation.addEventListener("click", (event) => {
      if (event.target.closest("a")) {
        menuButton.setAttribute("aria-expanded", "false");
        menuButton.setAttribute("aria-label", "Open navigation menu");
        navigation.classList.remove("is-open");
      }
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && navigation.classList.contains("is-open")) {
        menuButton.setAttribute("aria-expanded", "false");
        menuButton.setAttribute("aria-label", "Open navigation menu");
        navigation.classList.remove("is-open");
        menuButton.focus();
      }
    });
  }

  document.querySelectorAll(".faq-question").forEach((button) => {
    button.addEventListener("click", () => {
      const expanded = button.getAttribute("aria-expanded") === "true";
      const answer = document.getElementById(button.getAttribute("aria-controls"));
      button.setAttribute("aria-expanded", String(!expanded));
      answer?.setAttribute("aria-hidden", String(expanded));
    });
  });

  const revealItems = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const observer = new IntersectionObserver((entries, currentObserver) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          currentObserver.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -24px 0px" });
    revealItems.forEach((item) => observer.observe(item));
  } else {
    revealItems.forEach((item) => item.classList.add("is-visible"));
  }

  document.querySelectorAll("[data-current-year]").forEach((node) => {
    node.textContent = String(new Date().getFullYear());
  });

  document.querySelectorAll(".scanner-widget").forEach((scanner) => setupScanner(scanner));

  function setupScanner(scanner) {
    const fileInput = scanner.querySelector(".image-input");
    const dropzone = scanner.querySelector(".dropzone");
    const previewBox = scanner.querySelector(".preview-box");
    const preview = scanner.querySelector(".image-preview");
    const filename = scanner.querySelector(".file-name");
    const filesize = scanner.querySelector(".file-size");
    const removeButton = scanner.querySelector(".remove-file");
    const replaceButton = scanner.querySelector(".replace-file");
    const submitButton = scanner.querySelector(".scan-submit");
    const loading = scanner.querySelector(".loading-state");
    const error = scanner.querySelector(".error-state");
    const result = scanner.querySelector(".result-card");
    const resultContent = scanner.querySelector(".result-content");
    const anotherButton = scanner.querySelector(".scan-another");
    const contextField = scanner.querySelector(".context-field");
    let selectedFile = null;
    let previewUrl = null;
    let isSubmitting = false;

    const formatBytes = (bytes) => bytes < 1024 * 1024
      ? `${Math.max(1, Math.round(bytes / 1024))} KB`
      : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;

    function clearPreviewUrl() {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = null;
    }

    function setFile(file) {
      hideMessages();
      if (!file) return;
      const acceptedTypes = ["image/jpeg", "image/png", "image/webp"];
      if (!acceptedTypes.includes(file.type)) {
        showError("Choose a JPG, PNG, or WEBP image.");
        fileInput.value = "";
        return;
      }
      if (file.size > 8 * 1024 * 1024) {
        showError("Choose an image smaller than 8 MB.");
        fileInput.value = "";
        return;
      }
      clearPreviewUrl();
      selectedFile = file;
      previewUrl = URL.createObjectURL(file);
      preview.src = previewUrl;
      preview.alt = `Preview of ${file.name}`;
      filename.textContent = file.name;
      filesize.textContent = formatBytes(file.size);
      previewBox.hidden = false;
      dropzone.hidden = true;
      submitButton.disabled = false;
      result.hidden = true;
    }

    function hideMessages() {
      error.hidden = true;
      loading.hidden = true;
      result.hidden = true;
    }

    function showError(message) {
      hideMessages();
      error.textContent = message;
      error.hidden = false;
    }

    function resetScanner() {
      clearPreviewUrl();
      selectedFile = null;
      fileInput.value = "";
      preview.removeAttribute("src");
      previewBox.hidden = true;
      dropzone.hidden = false;
      submitButton.disabled = true;
      submitButton.textContent = "Analyze item";
      hideMessages();
      dropzone.focus({ preventScroll: true });
    }

    dropzone.addEventListener("click", () => fileInput.click());
    dropzone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        fileInput.click();
      }
    });
    fileInput.addEventListener("change", () => setFile(fileInput.files?.[0]));
    removeButton.addEventListener("click", resetScanner);
    replaceButton.addEventListener("click", () => {
      fileInput.value = "";
      fileInput.click();
    });
    anotherButton.addEventListener("click", resetScanner);

    ["dragenter", "dragover"].forEach((type) => dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      dropzone.classList.add("is-dragging");
    }));
    ["dragleave", "drop"].forEach((type) => dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      dropzone.classList.remove("is-dragging");
    }));
    dropzone.addEventListener("drop", (event) => setFile(event.dataTransfer?.files?.[0]));

    scanner.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!selectedFile || isSubmitting) return;
      isSubmitting = true;
      hideMessages();
      loading.hidden = false;
      submitButton.disabled = true;
      submitButton.textContent = "Analyzing…";

      const formData = new FormData();
      formData.append("image", selectedFile, selectedFile.name);
      formData.append("context", contextField.value);
      try {
        const response = await fetch("/api/analyze", { method: "POST", body: formData, headers: { Accept: "application/json" } });
        let payload;
        try { payload = await response.json(); } catch { payload = {}; }
        if (!response.ok) {
          const detail = typeof payload.detail === "string" ? payload.detail : "We could not analyze that image. Please try another clear photo.";
          throw new Error(detail);
        }
        renderResult(payload);
        result.hidden = false;
      } catch (cause) {
        const message = cause instanceof TypeError
          ? "We could not reach Smart Waste. Check that the app server is running, then try again."
          : cause.message || "We could not analyze that image. Please try again.";
        showError(message);
      } finally {
        loading.hidden = true;
        submitButton.disabled = !selectedFile;
        submitButton.textContent = "Analyze item";
        isSubmitting = false;
      }
    });

    function renderResult(data) {
      resultContent.replaceChildren();
      if (data.needs_review || data.confidence === "low") {
        const uncertainty = document.createElement("div");
        uncertainty.className = "uncertain-banner";
        uncertainty.textContent = "This match is uncertain. Use the guidance as a starting point and check the item label or your local waste service.";
        resultContent.append(uncertainty);
      }

      const heading = document.createElement("div");
      heading.className = "result-heading";
      const itemName = document.createElement("h4");
      itemName.textContent = data.item || "Unidentified item";
      const confidence = document.createElement("span");
      confidence.className = "confidence-tag";
      confidence.textContent = `${data.confidence || "unknown"} confidence`;
      heading.append(itemName, confidence);

      const fields = document.createElement("div");
      fields.className = "result-fields";
      [["Material", data.material], ["Visible condition", data.condition], ["Context", data.context || "Not provided"]].forEach(([label, value]) => {
        const field = document.createElement("div");
        field.className = "result-field";
        const fieldLabel = document.createElement("span");
        fieldLabel.textContent = label;
        const fieldValue = document.createElement("strong");
        fieldValue.textContent = value || "Not clear";
        field.append(fieldLabel, fieldValue);
        fields.append(field);
      });

      const recommendation = document.createElement("div");
      recommendation.className = "recommendation";
      const recommendationLabel = document.createElement("strong");
      recommendationLabel.textContent = "Recommended next step";
      const recommendationText = document.createElement("p");
      recommendationText.textContent = data.recommendation || "Check your local waste guidance.";
      recommendation.append(recommendationLabel, recommendationText);

      const reason = document.createElement("p");
      reason.className = "result-reason";
      reason.textContent = data.reason || "Disposal options can vary by location. Check your local collection guidance.";
      const preparation = document.createElement("p");
      preparation.className = "result-preparation";
      const prepLabel = document.createElement("b");
      prepLabel.textContent = "Before you go: ";
      preparation.append(prepLabel, document.createTextNode(data.preparation || "Check the local service instructions."));
      resultContent.append(heading, fields, recommendation, reason, preparation);
    }
  }
})();
