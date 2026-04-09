/**
 * TW-FORUM ENGINE - Particles System
 * Легкие частицы на фоне для атмосферности
 */

(function() {
    'use strict';

    const canvas = document.getElementById('particles-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let particles = [];
    let animationId;
    let mouse = { x: null, y: null };

    // Настройки
    const config = {
        particleCount: 60,
        maxDistance: 120,
        speed: 0.3,
        size: 1.5,
        color: '0, 255, 157', // RGB для accent
        opacity: 0.4
    };

    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }

    class Particle {
        constructor() {
            this.x = Math.random() * canvas.width;
            this.y = Math.random() * canvas.height;
            this.vx = (Math.random() - 0.5) * config.speed;
            this.vy = (Math.random() - 0.5) * config.speed;
            this.size = Math.random() * config.size + 0.5;
            this.opacity = Math.random() * config.opacity + 0.1;
        }

        update() {
            this.x += this.vx;
            this.y += this.vy;

            // Отскок от краев
            if (this.x < 0 || this.x > canvas.width) this.vx *= -1;
            if (this.y < 0 || this.y > canvas.height) this.vy *= -1;

            // Взаимодействие с мышью
            if (mouse.x !== null) {
                const dx = mouse.x - this.x;
                const dy = mouse.y - this.y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 150) {
                    const force = (150 - dist) / 150;
                    this.vx -= (dx / dist) * force * 0.02;
                    this.vy -= (dy / dist) * force * 0.02;
                }
            }
        }

        draw() {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${config.color}, ${this.opacity})`;
            ctx.fill();
        }
    }

    function init() {
        resize();
        particles = [];
        for (let i = 0; i < config.particleCount; i++) {
            particles.push(new Particle());
        }
    }

    function drawLines() {
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);

                if (dist < config.maxDistance) {
                    const opacity = (1 - dist / config.maxDistance) * 0.15;
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = `rgba(${config.color}, ${opacity})`;
                    ctx.lineWidth = 0.5;
                    ctx.stroke();
                }
            }
        }
    }

    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        particles.forEach(p => {
            p.update();
            p.draw();
        });
        
        drawLines();
        animationId = requestAnimationFrame(animate);
    }

    // Event Listeners
    window.addEventListener('resize', () => {
        resize();
    });

    window.addEventListener('mousemove', (e) => {
        mouse.x = e.clientX;
        mouse.y = e.clientY;
    });

    window.addEventListener('mouseleave', () => {
        mouse.x = null;
        mouse.y = null;
    });

    // Запуск
    init();
    animate();

    // Пауза при неактивной вкладке
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            cancelAnimationFrame(animationId);
        } else {
            animate();
        }
    });
})();