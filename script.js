// --- FIREBASE IMPORTS ---
import { initializeApp } from "https://www.gstatic.com/firebasejs/12.6.0/firebase-app.js";
import {
    getAuth,
    onAuthStateChanged,
    signOut,
} from "https://www.gstatic.com/firebasejs/12.6.0/firebase-auth.js";

// --- CONFIGURATION ---
const API_BASE = "http://127.0.0.1:5000/api";
const MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024; // 20 MB
const ALLOWED_MIME_TYPES = [
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
];
const THEME_KEY = "pdfToolkitTheme";

// Firebase Configuration
const firebaseConfig = {
    apiKey: "AIzaSyDFbFrZXqfLVM0QQGmIM5W3dkBHCOkgIGg",
    authDomain: "pdf-toolkit-90b52.firebaseapp.com",
    projectId: "pdf-toolkit-90b52",
    storageBucket: "pdf-toolkit-90b52.firebasestorage.app",
    messagingSenderId: "93639766122",
    appId: "1:93639766122:web:7f3105f91cd4de0feb5a13",
    measurementId: "G-5PVV5HW2DG",
};

// --- STATE MANAGEMENT ---
const root = document.documentElement;
const toastContainer = document.getElementById("toastContainer");
let mergeFiles = []; // Stores { file, invalid, error, uploading, progress, id, serverFileId }

// --- AUTHENTICATION ---
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

const authButtons = document.getElementById("authButtons");
const userDropdown = document.getElementById("userDropdown");
const userNameSpan = document.getElementById("userName");
const logoutBtn = document.getElementById("logoutBtn");

// Handle Auth State Changes
onAuthStateChanged(auth, (user) => {
    if (user) {
        // User is signed in
        if (authButtons) authButtons.classList.add("hidden");
        if (userDropdown) userDropdown.classList.remove("hidden");
        if (userNameSpan) {
            const nameToShow = user.displayName || user.email || "User";
            userNameSpan.textContent = nameToShow.split(" ")[0] || nameToShow;
        }
    } else {
        // User is signed out
        if (authButtons) authButtons.classList.remove("hidden");
        if (userDropdown) userDropdown.classList.add("hidden");
    }
});

// Handle Logout
if (logoutBtn) {
    logoutBtn.addEventListener("click", async () => {
        try {
            await signOut(auth);
            toast.show("Logged out successfully.", "success");
            // Optional: Redirect to home or refresh
        } catch (error) {
            console.error("Logout failed:", error);
            toast.show("Logout failed. Please try again.", "error");
        }
    });
}

// --- TOAST NOTIFICATION SYSTEM ---
class ToastManager {
    show(message, type = "info") {
        if (!this.container) return;
        const toast = document.createElement("div");
        toast.className = `toast ${type}`;
        toast.setAttribute("role", "status");

        const messageSpan = document.createElement("span");
        messageSpan.textContent = message;

        const closeButton = document.createElement("button");
        closeButton.className = "toast-close";
        closeButton.textContent = "×";
        closeButton.setAttribute("aria-label", "Dismiss notification");
        closeButton.onclick = () => toast.remove();

        toast.appendChild(messageSpan);
        toast.appendChild(closeButton);
        this.container.appendChild(toast);

        setTimeout(() => toast.remove(), 6000);
    }
    get container() {
        return document.getElementById("toastContainer");
    }
}
const toast = new ToastManager();

// --- THEME / DARK MODE ---
const themeToggle = document.getElementById("theme-toggle");

function applyTheme(theme) {
    const isDark = theme === "dark";
    root.setAttribute("data-theme", isDark ? "dark" : "light");
    if (themeToggle) {
        themeToggle.setAttribute("aria-pressed", isDark);
    }
}

// Initialize Theme
const savedTheme = localStorage.getItem(THEME_KEY);
if (savedTheme) {
    applyTheme(savedTheme);
} else {
    const prefersDark =
        window.matchMedia &&
        window.matchMedia("(prefers-color-scheme: dark)").matches;
    applyTheme(prefersDark ? "dark" : "light");
}

// Toggle Theme
if (themeToggle) {
    themeToggle.addEventListener("click", () => {
        const currentTheme =
            root.getAttribute("data-theme") === "dark" ? "dark" : "light";
        const newTheme = currentTheme === "light" ? "dark" : "light";
        localStorage.setItem(THEME_KEY, newTheme);
        applyTheme(newTheme);
    });
}

// --- DROPDOWN HANDLERS ---
function setupDropdown(buttonId, menuId) {
    const btn = document.getElementById(buttonId);
    const menu = document.getElementById(menuId);
    if (!btn || !menu) return;

    const toggleMenu = (open) => {
        const isOpen =
            open !== undefined ? open : menu.classList.contains("active");
        if (isOpen) {
            menu.classList.remove("active");
            btn.setAttribute("aria-expanded", "false");
        } else {
            menu.classList.add("active");
            btn.setAttribute("aria-expanded", "true");
            menu.querySelector("a, button")?.focus();
        }
    };

    btn.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleMenu();
    });

    menu.addEventListener("keydown", (e) => {
        const items = Array.from(
            menu.querySelectorAll('a[role="menuitem"], button[role="menuitem"]')
        );
        const currentIndex = items.indexOf(document.activeElement);

        if (e.key === "Escape") {
            toggleMenu(true);
            btn.focus();
        } else if (e.key === "ArrowDown") {
            e.preventDefault();
            const nextIndex = (currentIndex + 1) % items.length;
            items[nextIndex].focus();
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            const prevIndex = (currentIndex - 1 + items.length) % items.length;
            items[prevIndex].focus();
        }
    });

    document.addEventListener("click", (e) => {
        if (
            menu.classList.contains("active") &&
            !btn.contains(e.target) &&
            !menu.contains(e.target)
        ) {
            toggleMenu(true);
        }
    });
}

setupDropdown("langBtn", "langDropdown");
setupDropdown("userBtn", "userMenu");

// --- HAMBURGER MENU ---
const hamburger = document.getElementById("hamburger");
const navbarMenu = document.getElementById("navbarMenu");

if (hamburger && navbarMenu) {
    hamburger.addEventListener("click", () => {
        hamburger.classList.toggle("active");
        navbarMenu.classList.toggle("active");
        hamburger.setAttribute(
            "aria-expanded",
            navbarMenu.classList.contains("active")
        );
    });

    document.querySelectorAll(".navbar-menu a").forEach((link) => {
        link.addEventListener("click", () => {
            if (navbarMenu.classList.contains("active")) {
                hamburger.classList.remove("active");
                navbarMenu.classList.remove("active");
                hamburger.setAttribute("aria-expanded", "false");
            }
        });
    });
}

// --- FILE UPLOAD & TOOL LOGIC ---
const fileUploadInput = document.getElementById("fileUploadInput");
const startUploadBtn = document.getElementById("startUploadBtn");
const mergeDropZone = document.getElementById("mergeDropZone");
const mergeFileList = document.getElementById("mergeFileList");
const downloadBtn = document.getElementById("downloadBtn");

function isValidFile(file) {
    if (file.size > MAX_FILE_SIZE_BYTES) {
        toast.show(`File ${file.name} is too large (max 20MB).`, "error");
        return false;
    }
    if (!ALLOWED_MIME_TYPES.includes(file.type)) {
        toast.show(`File ${file.name} is not an allowed type.`, "error");
        return false;
    }
    return true;
}

function updateUploadButtonState() {
    if (startUploadBtn) {
        startUploadBtn.disabled =
            mergeFiles.length === 0 || mergeFiles.some((f) => f.invalid);
    }
}

function renderMergeFiles() {
    if (!mergeFileList) return;
    mergeFileList.innerHTML = "";
    mergeFiles.forEach((fileEntry, index) => {
        const fileItem = document.createElement("div");
        fileItem.className = "file-item";
        fileItem.id = `file-item-${index}`;

        const sizeInMB = (fileEntry.file.size / (1024 * 1024)).toFixed(2);

        fileItem.innerHTML = `
            <div class="file-item-info">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                    <polyline points="14 2 14 8 20 8"></polyline>
                </svg>
                <span title="${fileEntry.file.name}">${fileEntry.file.name}</span>
                <span class="text-xs text-gray-500">(${sizeInMB} MB)</span>
            </div>
            <div class="file-item-actions">
                ${!fileEntry.invalid && !fileEntry.uploading && !fileEntry.serverFileId
                ? `
                <button class="icon-btn" onclick="moveFileUp(this)" aria-label="Move up">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"></polyline></svg>
                </button>
                <button class="icon-btn" onclick="moveFileDown(this)" aria-label="Move down">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg>
                </button>
                `
                : ""
            }
                <button class="icon-btn text-red-500" onclick="removeFileByIndex(${index})" aria-label="Remove">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                </button>
            </div>
            <div class="file-status">
                ${fileEntry.invalid
                ? `<span style="color:var(--danger)">Invalid: ${fileEntry.error}</span>`
                : fileEntry.uploading
                    ? `Uploading...`
                    : fileEntry.serverFileId
                        ? `<span style="color:var(--success)">Uploaded</span>`
                        : `Ready`
            }
            </div>
        `;
        mergeFileList.appendChild(fileItem);
    });
    updateUploadButtonState();
}

function addMergeFiles(files) {
    const newValidFiles = [];
    Array.from(files).forEach((file) => {
        if (isValidFile(file)) {
            newValidFiles.push({
                file,
                invalid: false,
                uploading: false,
                progress: 0,
                id: Date.now() + Math.random(),
                serverFileId: null,
            });
        } else {
            mergeFiles.push({
                file,
                invalid: true,
                error:
                    file.size > MAX_FILE_SIZE_BYTES
                        ? "File too large"
                        : "Invalid file type",
                uploading: false,
                progress: 0,
                id: Date.now() + Math.random(),
                serverFileId: null,
            });
        }
    });

    mergeFiles = [...mergeFiles, ...newValidFiles];
    renderMergeFiles();
    if (newValidFiles.length > 0) {
        toast.show(`${newValidFiles.length} file(s) added.`, "success");
    }

    // Reset UI state for new files
    if (downloadBtn) downloadBtn.classList.add("hidden");
    if (startUploadBtn) startUploadBtn.classList.remove("hidden");
}

// Global scope functions for generated HTML interactions
window.removeFileByIndex = function (index) {
    mergeFiles.splice(index, 1);
    renderMergeFiles();
};

window.moveFileUp = function (btn) {
    const item = btn.closest(".file-item");
    const index = Array.from(mergeFileList.children).indexOf(item);
    if (index > 0) {
        [mergeFiles[index - 1], mergeFiles[index]] = [
            mergeFiles[index],
            mergeFiles[index - 1],
        ];
        renderMergeFiles();
    }
};

window.moveFileDown = function (btn) {
    const item = btn.closest(".file-item");
    const index = Array.from(mergeFileList.children).indexOf(item);
    if (index < mergeFiles.length - 1) {
        [mergeFiles[index + 1], mergeFiles[index]] = [
            mergeFiles[index],
            mergeFiles[index + 1],
        ];
        renderMergeFiles();
    }
};

// Drag and Drop Setup
if (mergeDropZone && fileUploadInput) {
    ["dragenter", "dragover", "dragleave", "drop"].forEach((eventName) => {
        mergeDropZone.addEventListener(
            eventName,
            (e) => {
                e.preventDefault();
                e.stopPropagation();
            },
            false
        );
    });

    ["dragenter", "dragover"].forEach((eventName) => {
        mergeDropZone.addEventListener(
            eventName,
            () => mergeDropZone.classList.add("active"),
            false
        );
    });

    ["dragleave", "drop"].forEach((eventName) => {
        mergeDropZone.addEventListener(
            eventName,
            () => mergeDropZone.classList.remove("active"),
            false
        );
    });

    mergeDropZone.addEventListener(
        "drop",
        (e) => addMergeFiles(e.dataTransfer.files),
        false
    );
    mergeDropZone.addEventListener("click", () => fileUploadInput.click());
    mergeDropZone.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            fileUploadInput.click();
        }
    });

    fileUploadInput.onchange = (e) => {
        addMergeFiles(e.target.files);
        e.target.value = null;
    };
}

// --- API INTEGRATION ---

async function uploadFile(fileEntry) {
    const formData = new FormData();
    formData.append("file", fileEntry.file);

    try {
        const response = await fetch(`${API_BASE}/upload`, {
            method: "POST",
            body: formData,
        });

        if (!response.ok) {
            throw new Error(`Upload failed with status: ${response.status}`);
        }

        const data = await response.json();
        // Assuming backend returns { fileId: "..." } or { success: true, fileId: "..." }
        if (data.fileId) {
            return data.fileId;
        } else if (data.success && data.fileId) {
            return data.fileId;
        } else {
            throw new Error(data.error || "Upload failed: No fileId returned");
        }
    } catch (error) {
        console.error("Upload error:", error);
        throw error;
    }
}

async function processMerge(fileIds) {
    try {
        const response = await fetch(`${API_BASE}/tools/merge`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                fileIds: fileIds,
                params: {}, // Empty params for simple merge
            }),
        });

        if (!response.ok) {
            throw new Error(`Merge failed with status: ${response.status}`);
        }

        const data = await response.json();
        if (data.download_url) {
            return data.download_url;
        } else {
            throw new Error(data.error || "Processing failed: No download URL");
        }
    } catch (error) {
        console.error("Merge error:", error);
        throw error;
    }
}

if (startUploadBtn) {
    startUploadBtn.addEventListener("click", async () => {
        if (mergeFiles.length === 0 || mergeFiles.some((f) => f.invalid)) {
            toast.show("Please fix invalid files before proceeding.", "error");
            return;
        }

        startUploadBtn.disabled = true;
        const originalText = startUploadBtn.textContent;
        startUploadBtn.textContent = "Uploading...";
        let uploadErrors = false;

        // 1. Upload Phase
        for (const fileEntry of mergeFiles) {
            if (fileEntry.serverFileId) continue; // Already uploaded

            fileEntry.uploading = true;
            renderMergeFiles();

            try {
                const fileId = await uploadFile(fileEntry);
                fileEntry.serverFileId = fileId;
                fileEntry.uploading = false;
                renderMergeFiles();
            } catch (error) {
                fileEntry.uploading = false;
                fileEntry.invalid = true;
                fileEntry.error = "Upload Failed";
                uploadErrors = true;
                renderMergeFiles();
            }
        }

        if (uploadErrors) {
            startUploadBtn.textContent = "Retry Upload & Merge";
            startUploadBtn.disabled = false;
            toast.show("Some files failed to upload.", "error");
            return;
        }

        // 2. Processing Phase
        startUploadBtn.textContent = "Processing...";
        const fileIds = mergeFiles.map((f) => f.serverFileId);

        try {
            const downloadUrl = await processMerge(fileIds);

            // 3. Download Phase Setup (Manual Download Only)
            startUploadBtn.classList.add("hidden");
            startUploadBtn.textContent = originalText; // Reset for next time
            startUploadBtn.disabled = false;

            if (downloadBtn) {
                downloadBtn.classList.remove("hidden");
                // Remove previous event listeners by re-assigning onclick
                downloadBtn.onclick = (e) => {
                    e.preventDefault();
                    // Open the backend download URL in a new tab
                    window.open(downloadUrl, "_blank");
                    toast.show("Download started", "success");
                };
            }
            toast.show("Merge complete! Click download to save your file.", "success");
        } catch (error) {
            startUploadBtn.textContent = "Retry Merge";
            startUploadBtn.disabled = false;
            toast.show("Merge failed. Please try again.", "error");
        }
    });
}

// --- SEARCH & CATEGORY FILTERS ---
(function () {
    const searchInput = document.getElementById("searchTools");
    const toolCards = Array.from(document.querySelectorAll(".tool-card"));
    const categoryButtons = Array.from(document.querySelectorAll(".category-btn"));
    const toolsGrid = document.getElementById("toolsGrid");

    function filterTools() {
        const q = (searchInput?.value || "").toLowerCase().trim();
        const activeCategory =
            document.querySelector(".category-btn.active")?.dataset.category || "all";
        let anyVisible = false;

        toolCards.forEach((card) => {
            const title = (card.querySelector("h3")?.textContent || "").toLowerCase();
            const desc = (card.querySelector("p")?.textContent || "").toLowerCase();
            const toolCats = (card.dataset.category || "").toLowerCase();

            const matchesSearch = !q || title.includes(q) || desc.includes(q);
            const matchesCat =
                activeCategory === "all" || toolCats.includes(activeCategory.toLowerCase());

            if (matchesSearch && matchesCat) {
                card.style.display = "";
                card.classList.add("fade-in");
                requestAnimationFrame(() => card.classList.add("visible"));
                anyVisible = true;
            } else {
                card.style.display = "none";
                card.classList.remove("visible");
            }
        });

        // Handle no results
        let msg = document.getElementById("noToolsMsg");
        if (!anyVisible) {
            if (!msg && toolsGrid) {
                msg = document.createElement("div");
                msg.id = "noToolsMsg";
                msg.className = "no-tools-message";
                msg.textContent = "No tools found matching your criteria.";
                msg.style.textAlign = "center";
                msg.style.padding = "2rem";
                msg.style.gridColumn = "1 / -1";
                toolsGrid.appendChild(msg);
            }
            if (msg) requestAnimationFrame(() => msg.classList.add("visible"));
        } else if (msg) {
            msg.remove();
        }
    }

    if (searchInput) {
        searchInput.addEventListener("input", filterTools);
    }

    categoryButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            categoryButtons.forEach((b) => {
                b.classList.remove("active");
                b.setAttribute("aria-pressed", "false");
            });
            btn.classList.add("active");
            btn.setAttribute("aria-pressed", "true");
            filterTools();
        });
    });

    // Initial animations
    const elements = document.querySelectorAll(
        "section, .tool-card, .feature-card"
    );
    const observer = new IntersectionObserver(
        (entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.classList.add("visible");
                    observer.unobserve(entry.target);
                }
            });
        },
        { threshold: 0.1 }
    );

    elements.forEach((el) => {
        el.classList.add("fade-in", "slide-up");
        observer.observe(el);
    });
})();

// --- INITIALIZATION ---
document.addEventListener("DOMContentLoaded", () => {
    const yearEl = document.getElementById("currentYear");
    if (yearEl) yearEl.textContent = new Date().getFullYear();

    // Smooth scroll
    document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
        anchor.addEventListener("click", function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute("href"));
            if (target) {
                target.scrollIntoView({ behavior: "smooth" });
                // Close mobile menu
                if (navbarMenu?.classList.contains("active")) {
                    hamburger.click();
                }
            }
        });
    });
});

