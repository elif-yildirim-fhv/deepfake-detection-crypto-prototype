document.addEventListener("click", (e) => {
  if (e.target.matches(".btn-copy, .btn-copy-inline")) {
    const targetId = e.target.dataset.target;
    const el = document.getElementById(targetId);
    const text = el.tagName === "TEXTAREA" || el.tagName === "INPUT"
      ? el.value
      : el.textContent;
    navigator.clipboard.writeText(text).then(() => {
      const orig = e.target.textContent;
      e.target.textContent = "Kopiert!";
      setTimeout(() => (e.target.textContent = orig), 1500);
    });
  }
});

document.getElementById("btn-generate-keys").addEventListener("click", async () => {
  const btn = document.getElementById("btn-generate-keys");
  btn.disabled = true;
  btn.textContent = "Generiere...";

  try {
    const res = await fetch("/api/generate-keys", { method: "POST" });
    const data = await res.json();

    document.getElementById("private-key").value = data.private_key;
    document.getElementById("public-key").value = data.public_key;
    document.getElementById("keys-output").classList.remove("hidden");

    document.getElementById("sign-private-key").value = data.private_key;
    document.getElementById("verify-public-key").value = data.public_key;
  } catch {
    alert("Fehler beim Generieren der Schlüssel.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Schlüsselpaar generieren";
  }
});

document.getElementById("sign-file").addEventListener("change", (e) => {
  const file = e.target.files[0];
  const badge = document.getElementById("sign-file-info");
  if (!file) { badge.classList.add("hidden"); return; }

  const type = file.type;
  badge.classList.remove("hidden", "image", "audio", "video", "other");

  if (type.startsWith("image/")) {
    badge.className = "file-type-badge image";
    badge.textContent = "✓ Bilddatei erkannt";
  } else if (type.startsWith("audio/")) {
    badge.className = "file-type-badge audio";
    badge.textContent = "✓ Audiodatei erkannt";
  } else if (type.startsWith("video/")) {
    badge.className = "file-type-badge video";
    badge.textContent = "✓ Videodatei erkannt";
  } else {
    badge.className = "file-type-badge other";
    badge.textContent = "✓ Datei erkannt";
  }
});

document.getElementById("btn-sign").addEventListener("click", async () => {
  const file = document.getElementById("sign-file").files[0];
  const privateKey = document.getElementById("sign-private-key").value.trim();

  if (!file) return alert("Bitte eine Datei auswählen.");
  if (!privateKey) return alert("Bitte den Private Key eingeben.");

  const btn = document.getElementById("btn-sign");
  btn.disabled = true;
  btn.textContent = "Signiere...";

  const formData = new FormData();
  formData.append("file", file);
  formData.append("private_key", privateKey);

  try {
    const res = await fetch("/api/sign", { method: "POST", body: formData });
    const data = await res.json();

    if (data.error) {
      alert("Fehler: " + data.error);
      return;
    }

    document.getElementById("sign-filename").textContent = data.filename;
    document.getElementById("sign-hash").textContent = data.sha256;
    
    if (data.phash) {
      document.getElementById("sign-phash").textContent = data.phash;
      document.getElementById("sign-phash-row").style.display = "flex";
      document.getElementById("verify-phash").value = data.phash;
      document.getElementById("verify-phash-group").style.display = "block";
    } else {
      document.getElementById("sign-phash-row").style.display = "none";
      document.getElementById("verify-phash").value = "";
      document.getElementById("verify-phash-group").style.display = "none";
    }

    document.getElementById("sign-signature").value = data.signature;
    document.getElementById("sign-result").classList.remove("hidden");

    document.getElementById("verify-hash").value = data.sha256;
    document.getElementById("verify-signature").value = data.signature;
  } catch {
    alert("Netzwerkfehler beim Signieren.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Datei signieren";
  }
});

document.getElementById("btn-tamper").addEventListener("click", async () => {
  const file = document.getElementById("sign-file").files[0];
  if (!file) return alert("Bitte zuerst eine Datei signieren (Schritt 2).");

  const btn = document.getElementById("btn-tamper");
  btn.disabled = true;
  btn.textContent = "Manipuliere...";

  const tamperType = document.getElementById("tamper-type").value;
  const formData = new FormData();
  formData.append("file", file);
  formData.append("attack_type", tamperType);

  try {
    const res = await fetch("/api/tamper", { method: "POST", body: formData });
    if (!res.ok) { alert("Fehler beim Manipulieren."); return; }

    const method = res.headers.get("X-Tamper-Method") || "";
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename="?([^"]+)"?/);
    a.download = match ? match[1] : "manipuliert";
    a.href = url;
    a.click();
    URL.revokeObjectURL(url);

    if (method) {
      const info = document.getElementById("tamper-method");
      info.textContent = "Angewandte Manipulation: " + method;
      info.classList.remove("hidden");
    }
  } catch {
    alert("Netzwerkfehler.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Datei manipulieren & herunterladen";
  }
});
document.getElementById("btn-verify").addEventListener("click", async () => {
  const file = document.getElementById("verify-file").files[0];
  const publicKey = document.getElementById("verify-public-key").value.trim();
  const hash = document.getElementById("verify-hash").value.trim();
  const pHash = document.getElementById("verify-phash").value.trim();
  const signature = document.getElementById("verify-signature").value.trim();

  if (!file) return alert("Bitte eine Datei auswählen.");
  if (!publicKey) return alert("Bitte den Public Key eingeben.");
  if (!hash) return alert("Bitte den originalen SHA-256 Hash eingeben.");
  if (!signature) return alert("Bitte die Signatur eingeben.");

  const btn = document.getElementById("btn-verify");
  btn.disabled = true;
  btn.textContent = "Prüfe...";

  const formData = new FormData();
  formData.append("file", file);
  formData.append("public_key", publicKey);
  formData.append("sha256", hash);
  if (pHash) formData.append("phash", pHash);
  formData.append("signature", signature);

  try {
    const res = await fetch("/api/verify", { method: "POST", body: formData });
    const data = await res.json();

    if (data.error) {
      alert("Fehler: " + data.error);
      return;
    }

    const verdict = document.getElementById("verdict");
    verdict.className = "verdict";

    if (data.integrity_ok && data.signature_ok) {
      verdict.classList.add("ok");
      verdict.textContent = "✓ Datei ist unverändert und Signatur ist gültig.";
    } else if (!data.integrity_ok && data.signature_ok) {
      verdict.classList.add("fail");
      verdict.textContent = "✗ Datei wurde manipuliert! Hash stimmt nicht überein.";
    } else if (data.integrity_ok && !data.signature_ok) {
      verdict.classList.add("warn-box");
      verdict.textContent = "⚠ Hash stimmt überein, aber Signatur ist ungültig.";
    } else {
      verdict.classList.add("fail");
      verdict.textContent = "✗ Datei manipuliert und Signatur ungültig.";
    }

    if (data.original_phash && data.original_phash !== "None" && data.current_phash) {
      const phashRow = document.getElementById("verify-phash-row");
      const phashStatus = document.getElementById("verify-phash-status");
      phashRow.style.display = "flex";
      
      let phashText = `<span class="info" style="font-size:0.85em; margin-left: 10px;">(Abweichung: ${data.phash_diff} / Schwelle 3)</span>`;
      if (data.phash_ok) {
          phashStatus.innerHTML = `<span class="badge ok">Inhalt OK</span> ${phashText}`;
          if (!data.integrity_ok) {
              verdict.className = "verdict warn-box";
              verdict.textContent = "⚠ Kryptografischer Hash falsch (z.B. komprimiert), aber Bildinhalt ist intakt (kein Deepfake).";
          }
      } else {
          phashStatus.innerHTML = `<span class="badge fail">Manipuliert</span> ${phashText}`;
          if (!data.integrity_ok) {
              verdict.className = "verdict fail";
              verdict.textContent = "✗ Datei UND Bildinhalt manipuliert (Deepfake erkannt!).";
          }
      }
    } else {
      document.getElementById("verify-phash-row").style.display = "none";
    }

    document.getElementById("verify-original-hash").textContent = data.original_hash;
    document.getElementById("verify-current-hash").textContent = data.current_hash;
    document.getElementById("verify-integrity").innerHTML =
      `<span class="badge ${data.integrity_ok ? "ok" : "fail"}">${data.integrity_ok ? "OK" : "FEHLGESCHLAGEN"}</span>`;
    document.getElementById("verify-sig-status").innerHTML =
      `<span class="badge ${data.signature_ok ? "ok" : "fail"}">${data.signature_ok ? "Gültig" : "Ungültig"}</span>`;

    document.getElementById("verify-result").classList.remove("hidden");
  } catch {
    alert("Netzwerkfehler beim Prüfen.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Prüfen";
  }
});
