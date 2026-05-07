/**
 * MedCare Premium - Interactive Features
 */

document.addEventListener('DOMContentLoaded', function() {
    // ========================================
    // CURSOR EFFECT
    // ========================================
    const cursor = document.querySelector('.cursor');
    const cursorFollower = document.querySelector('.cursor-follower');

    if (window.matchMedia('(pointer: fine)').matches) {
        let mouseX = 0, mouseY = 0;
        let cursorX = 0, cursorY = 0;
        let followerX = 0, followerY = 0;

        document.addEventListener('mousemove', (e) => {
            mouseX = e.clientX;
            mouseY = e.clientY;
        });

        function animateCursor() {
            cursorX += (mouseX - cursorX) * 0.2;
            cursorY += (mouseY - cursorY) * 0.2;
            followerX += (mouseX - followerX) * 0.1;
            followerY += (mouseY - followerY) * 0.1;

            cursor.style.transform = `translate(${cursorX - 10}px, ${cursorY - 10}px)`;
            cursorFollower.style.transform = `translate(${followerX - 20}px, ${followerY - 20}px)`;

            requestAnimationFrame(animateCursor);
        }

        animateCursor();

        // Hover effects
        const hoverElements = document.querySelectorAll('a, button, .servico-card, .especialista-card');
        hoverElements.forEach(el => {
            el.addEventListener('mouseenter', () => {
                cursor.style.transform = `translate(${cursorX - 10}px, ${cursorY - 10}px) scale(1.5)`;
                cursor.style.borderColor = 'var(--accent)';
            });
            el.addEventListener('mouseleave', () => {
                cursor.style.transform = `translate(${cursorX - 10}px, ${cursorY - 10}px) scale(1)`;
                cursor.style.borderColor = 'var(--accent)';
            });
        });
    }

    // ========================================
    // PROGRESS BAR
    // ========================================
    const progressFill = document.querySelector('.progress-fill');

    window.addEventListener('scroll', () => {
        const scrollTop = window.pageYOffset;
        const docHeight = document.documentElement.scrollHeight - window.innerHeight;
        const scrollPercent = (scrollTop / docHeight) * 100;
        progressFill.style.width = scrollPercent + '%';
    });

    // ========================================
    // HEADER SCROLL
    // ========================================
    const header = document.getElementById('header');

    window.addEventListener('scroll', () => {
        if (window.pageYOffset > 50) {
            header.classList.add('scrolled');
        } else {
            header.classList.remove('scrolled');
        }
    });

    // ========================================
    // MOBILE MENU
    // ========================================
    const menuToggle = document.getElementById('menuToggle');
    const navMenu = document.getElementById('navMenu');

    menuToggle.addEventListener('click', () => {
        menuToggle.classList.toggle('active');
        navMenu.classList.toggle('active');
    });

    // Close menu on link click
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', () => {
            menuToggle.classList.remove('active');
            navMenu.classList.remove('active');
        });
    });

    // ========================================
    // COUNTER ANIMATION
    // ========================================
    const counters = document.querySelectorAll('.counter');
    const statsSection = document.querySelector('.stats');
    let counted = false;

    function animateCounter(el, target) {
        let current = 0;
        const increment = target / 50;
        const timer = setInterval(() => {
            current += increment;
            if (current >= target) {
                el.textContent = target.toLocaleString();
                clearInterval(timer);
            } else {
                el.textContent = Math.floor(current).toLocaleString();
            }
        }, 30);
    }

    const statsObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting && !counted) {
                counted = true;
                counters.forEach(counter => {
                    const target = parseInt(counter.parentElement.parentElement.dataset.count);
                    animateCounter(counter, target);
                });
            }
        });
    }, { threshold: 0.5 });

    if (statsSection) {
        statsObserver.observe(statsSection);
    }

    // ========================================
    // SERVIÇOS SLIDER
    // ========================================
    const servicosTrack = document.querySelector('.servicos-track');
    const prevBtn = document.querySelector('.slider-btn.prev');
    const nextBtn = document.querySelector('.slider-btn.next');

    if (servicosTrack && prevBtn && nextBtn) {
        const cardWidth = 320;

        nextBtn.addEventListener('click', () => {
            servicosTrack.scrollBy({ left: cardWidth, behavior: 'smooth' });
        });

        prevBtn.addEventListener('click', () => {
            servicosTrack.scrollBy({ left: -cardWidth, behavior: 'smooth' });
        });
    }

    // ========================================
    // DEPOIMENTOS SLIDER
    // ========================================
    const depoimentos = document.querySelectorAll('.depoimento-card');
    const depoPrev = document.querySelector('.depo-btn.prev');
    const depoNext = document.querySelector('.depo-btn.next');
    let currentDepo = 0;

    function showDepoimento(index) {
        depoimentos.forEach((depo, i) => {
            depo.classList.remove('active');
            if (i === index) {
                depo.classList.add('active');
            }
        });
    }

    if (depoPrev && depoNext) {
        depoPrev.addEventListener('click', () => {
            currentDepo = (currentDepo - 1 + depoimentos.length) % depoimentos.length;
            showDepoimento(currentDepo);
        });

        depoNext.addEventListener('click', () => {
            currentDepo = (currentDepo + 1) % depoimentos.length;
            showDepoimento(currentDepo);
        });
    }

    // Auto rotate depoimentos
    setInterval(() => {
        if (depoimentos.length > 0) {
            currentDepo = (currentDepo + 1) % depoimentos.length;
            showDepoimento(currentDepo);
        }
    }, 6000);

    // ========================================
    // SMOOTH SCROLL
    // ========================================
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            const href = this.getAttribute('href');
            if (href === '#') return;

            const target = document.querySelector(href);
            if (target) {
                e.preventDefault();
                const headerHeight = header.offsetHeight;
                const targetPosition = target.getBoundingClientRect().top + window.pageYOffset - headerHeight;

                window.scrollTo({
                    top: targetPosition,
                    behavior: 'smooth'
                });
            }
        });
    });

    // ========================================
    // SCROLL REVEAL ANIMATION
    // ========================================
    const revealElements = document.querySelectorAll('.servico-card, .especialista-card, .stat-item');

    const revealObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, { threshold: 0.1 });

    revealElements.forEach(el => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(20px)';
        el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        revealObserver.observe(el);
    });

    // ========================================
    // ACTIVE NAV LINK
    // ========================================
    const sections = document.querySelectorAll('section[id]');
    const navLinks = document.querySelectorAll('.nav-link');

    function setActiveLink() {
        const scrollPos = window.pageYOffset + header.offsetHeight + 100;

        sections.forEach(section => {
            const sectionTop = section.offsetTop;
            const sectionHeight = section.offsetHeight;
            const sectionId = section.getAttribute('id');

            if (scrollPos >= sectionTop && scrollPos < sectionTop + sectionHeight) {
                navLinks.forEach(link => {
                    link.classList.remove('active');
                    if (link.getAttribute('href') === `#${sectionId}`) {
                        link.classList.add('active');
                    }
                });
            }
        });
    }

    window.addEventListener('scroll', setActiveLink);

    // ========================================
    // PARALLAX EFFECT
    // ========================================
    const heroShapes = document.querySelectorAll('.hero-shape');

    window.addEventListener('scroll', () => {
        const scrolled = window.pageYOffset;
        heroShapes.forEach((shape, index) => {
            const speed = 0.1 * (index + 1);
            shape.style.transform = `translateY(${scrolled * speed}px)`;
        });
    });
});
