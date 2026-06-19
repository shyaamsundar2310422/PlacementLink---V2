(function () {
    const storageKey = "placementlink-theme";
    const root = document.documentElement;
    const toggle = document.getElementById("themeToggle");
    const canvas = document.getElementById("bgMeshCanvas");

    function applyTheme(theme) {
        root.setAttribute("data-theme", theme);
        if (toggle) {
            toggle.setAttribute("aria-pressed", String(theme === "light"));
        }
    }

    function getPreferredTheme() {
        const savedTheme = localStorage.getItem(storageKey);
        if (savedTheme === "light" || savedTheme === "dark") {
            return savedTheme;
        }

        return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    }

    const initialTheme = getPreferredTheme();
    applyTheme(initialTheme);

    if (toggle) {
        toggle.addEventListener("click", function () {
            const currentTheme = root.getAttribute("data-theme") === "light" ? "light" : "dark";
            const nextTheme = currentTheme === "light" ? "dark" : "light";
            localStorage.setItem(storageKey, nextTheme);
            applyTheme(nextTheme);
        });
    }

    const reviewToggle = document.getElementById("studentReviewBell");
    const reviewDropdown = document.getElementById("studentReviewDropdown");

    if (reviewToggle && reviewDropdown) {
        function closeReviewDropdown() {
            reviewDropdown.hidden = true;
            reviewToggle.setAttribute("aria-expanded", "false");
        }

        reviewToggle.addEventListener("click", function () {
            const nextHidden = !reviewDropdown.hidden;
            reviewDropdown.hidden = nextHidden;
            reviewToggle.setAttribute("aria-expanded", nextHidden ? "false" : "true");
        });

        document.addEventListener("click", function (event) {
            if (!reviewDropdown.hidden && !reviewToggle.contains(event.target) && !reviewDropdown.contains(event.target)) {
                closeReviewDropdown();
            }
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                closeReviewDropdown();
            }
        });
    }

    if (canvas) {
        const context = canvas.getContext("2d");
        const motionReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const pointer = {
            x: window.innerWidth * 0.5,
            y: window.innerHeight * 0.5,
            radius: 160,
            active: false
        };
        let points = [];
        let animationFrame = null;

        function resizeCanvas() {
            const dpr = window.devicePixelRatio || 1;
            canvas.width = Math.floor(window.innerWidth * dpr);
            canvas.height = Math.floor(window.innerHeight * dpr);
            context.setTransform(dpr, 0, 0, dpr, 0, 0);
            buildMesh();
        }

        function buildMesh() {
            points = [];
            const width = window.innerWidth;
            const height = window.innerHeight;
            const spacing = Math.max(26, Math.min(44, Math.floor(width / 34)));
            const rowStep = Math.round(spacing * 0.72);
            const skew = Math.round(spacing * 0.48);

            for (let y = -rowStep; y <= height + rowStep; y += rowStep) {
                const rowIndex = Math.round(y / rowStep);
                const offset = rowIndex % 2 === 0 ? 0 : skew;
                for (let x = -spacing; x <= width + spacing; x += spacing) {
                    points.push({
                        baseX: x + offset,
                        baseY: y,
                        x: x + offset,
                        y: y,
                        vx: 0,
                        vy: 0
                    });
                }
            }
        }

        function getMeshColors() {
            const lightTheme = root.getAttribute("data-theme") === "light";
            return lightTheme
                ? {
                    line: "rgba(79, 70, 229, 0.12)",
                    activeLine: "rgba(79, 70, 229, 0.22)",
                    dot: "rgba(79, 70, 229, 0.30)",
                    activeDot: "rgba(5, 150, 105, 0.42)"
                }
                : {
                    line: "rgba(148, 163, 184, 0.09)",
                    activeLine: "rgba(99, 102, 241, 0.22)",
                    dot: "rgba(148, 163, 184, 0.26)",
                    activeDot: "rgba(16, 185, 129, 0.40)"
                };
        }

        function updatePoints() {
            const easing = motionReduced ? 0.08 : 0.11;
            const pullStrength = motionReduced ? 0.012 : 0.018;
            for (const point of points) {
                let targetX = point.baseX;
                let targetY = point.baseY;

                if (pointer.active) {
                    const dx = pointer.x - point.baseX;
                    const dy = pointer.y - point.baseY;
                    const distance = Math.hypot(dx, dy);
                    if (distance < pointer.radius) {
                        const influence = (1 - distance / pointer.radius) ** 2;
                        targetX += dx * pullStrength * 34 * influence;
                        targetY += dy * pullStrength * 34 * influence;
                    }
                }

                point.vx += (targetX - point.x) * easing;
                point.vy += (targetY - point.y) * easing;
                point.vx *= 0.74;
                point.vy *= 0.74;
                point.x += point.vx;
                point.y += point.vy;
            }
        }

        function drawMesh() {
            const width = window.innerWidth;
            const height = window.innerHeight;
            const colors = getMeshColors();
            const connectionDistance = 54;
            context.clearRect(0, 0, width, height);

            for (let i = 0; i < points.length; i += 1) {
                const point = points[i];
                for (let j = i + 1; j < points.length; j += 1) {
                    const neighbor = points[j];
                    const dx = neighbor.x - point.x;
                    const dy = neighbor.y - point.y;
                    const distance = Math.hypot(dx, dy);
                    if (distance > connectionDistance) {
                        continue;
                    }

                    const midpointX = (point.x + neighbor.x) * 0.5;
                    const midpointY = (point.y + neighbor.y) * 0.5;
                    const pointerDistance = Math.hypot(pointer.x - midpointX, pointer.y - midpointY);
                    const active = pointer.active && pointerDistance < pointer.radius * 0.92;
                    context.strokeStyle = active ? colors.activeLine : colors.line;
                    context.lineWidth = active ? 0.9 : 0.65;
                    context.beginPath();
                    context.moveTo(point.x, point.y);
                    context.lineTo(neighbor.x, neighbor.y);
                    context.stroke();
                }
            }

            for (const point of points) {
                const pointerDistance = Math.hypot(pointer.x - point.x, pointer.y - point.y);
                const active = pointer.active && pointerDistance < pointer.radius;
                context.fillStyle = active ? colors.activeDot : colors.dot;
                context.beginPath();
                context.arc(point.x, point.y, active ? 1.7 : 1.15, 0, Math.PI * 2);
                context.fill();
            }
        }

        function animate() {
            updatePoints();
            drawMesh();
            animationFrame = window.requestAnimationFrame(animate);
        }

        window.addEventListener("mousemove", function (event) {
            pointer.x = event.clientX;
            pointer.y = event.clientY;
            pointer.active = true;
        });

        window.addEventListener("mouseleave", function () {
            pointer.active = false;
        });

        window.addEventListener("touchmove", function (event) {
            if (!event.touches.length) {
                return;
            }
            pointer.x = event.touches[0].clientX;
            pointer.y = event.touches[0].clientY;
            pointer.active = true;
        }, { passive: true });

        window.addEventListener("touchend", function () {
            pointer.active = false;
        }, { passive: true });

        window.addEventListener("resize", function () {
            resizeCanvas();
        });

        resizeCanvas();
        if (animationFrame) {
            window.cancelAnimationFrame(animationFrame);
        }
        animate();
    }
})();
