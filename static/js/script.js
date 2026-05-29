// ═══════════════════════════════════
// 🌸 星辰小窝 · JavaScript
// ═══════════════════════════════════

// ── Mobile Menu ──
function toggleMobileMenu() {
    const menu = document.getElementById('mobileMenu');
    menu.classList.toggle('active');
    document.body.style.overflow = menu.classList.contains('active') ? 'hidden' : '';
}

// ── Flash Messages Auto-Dismiss ──
document.addEventListener('DOMContentLoaded', function() {
    // Auto-dismiss flash messages after 5 seconds
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach(function(msg) {
        setTimeout(function() {
            if (msg.parentElement) {
                msg.style.transition = 'all 0.3s ease';
                msg.style.opacity = '0';
                msg.style.transform = 'translateY(-10px)';
                setTimeout(function() {
                    if (msg.parentElement) msg.remove();
                }, 300);
            }
        }, 5000);
    });
});

// ── File Upload Preview ──
function updateFileHint(input) {
    const hint = document.getElementById('fileHint');
    if (input.files && input.files[0]) {
        const file = input.files[0];
        hint.textContent = '已选择: ' + file.name + ' (' + formatFileSize(file.size) + ')';
        hint.style.color = 'var(--blue-pri, #5B7FFF)';
    } else {
        hint.textContent = '未选择文件';
        hint.style.color = '';
    }
}

function previewAvatar(input) {
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const preview = document.querySelector('.avatar-edit-preview');
            if (preview) {
                preview.innerHTML = '<img src="' + e.target.result + '" alt="preview" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">';
            }
        };
        reader.readAsDataURL(input.files[0]);

        // Also update hint
        const hint = document.querySelector('.file-upload-area-sm span');
        if (hint) {
            hint.textContent = '📷 ' + input.files[0].name;
        }
    }
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// ── Image Modal ──
function openImageModal(src) {
    const modal = document.getElementById('imageModal');
    const modalImg = document.getElementById('modalImage');
    if (modal && modalImg) {
        modalImg.src = src;
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

function closeImageModal() {
    const modal = document.getElementById('imageModal');
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

// Close modal with Escape key
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeImageModal();
    }
});

// ── Smooth Scroll for Anchor Links ──
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('a[href^="#"]').forEach(function(anchor) {
        anchor.addEventListener('click', function(e) {
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                e.preventDefault();
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });
});

// ── Textarea Auto-Resize ──
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('textarea').forEach(function(textarea) {
        textarea.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = this.scrollHeight + 'px';
        });
    });
});
