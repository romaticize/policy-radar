/**
 * PolicyRadar Performance Fixes
 * ==============================
 * 
 * Fixes for Chrome glitching over time.
 * Add this script at the end of index.html, before </body>
 * 
 * Issues Fixed:
 * 1. Infinite CSS animations causing GPU strain
 * 2. IntersectionObserver memory leak
 * 3. Unused animation frames accumulating
 * 4. Tab visibility handling for animations
 */

(function() {
    'use strict';

    console.log('[PerfFix] Loading performance fixes...');

    // ============================================
    // FIX 1: Pause animations when tab is hidden
    // ============================================
    
    const animatedElements = new Set();
    let animationsPaused = false;

    function pauseAllAnimations() {
        if (animationsPaused) return;
        
        // Find all elements with infinite animations
        const allElements = document.querySelectorAll('*');
        allElements.forEach(el => {
            const style = getComputedStyle(el);
            if (style.animationIterationCount === 'infinite' && 
                style.animationPlayState === 'running') {
                el.style.animationPlayState = 'paused';
                animatedElements.add(el);
            }
        });
        
        animationsPaused = true;
        console.log('[PerfFix] Paused', animatedElements.size, 'infinite animations');
    }

    function resumeAllAnimations() {
        if (!animationsPaused) return;
        
        animatedElements.forEach(el => {
            if (el.isConnected) {
                el.style.animationPlayState = 'running';
            }
        });
        animatedElements.clear();
        animationsPaused = false;
        console.log('[PerfFix] Resumed animations');
    }

    // Pause animations when tab is hidden
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            pauseAllAnimations();
        } else {
            resumeAllAnimations();
        }
    });

    // ============================================
    // FIX 2: Clean up IntersectionObservers
    // ============================================
    
    // Store all observers for cleanup
    const observers = new Set();
    const originalIntersectionObserver = window.IntersectionObserver;

    window.IntersectionObserver = function(callback, options) {
        const observer = new originalIntersectionObserver(callback, options);
        observers.add(observer);
        
        // Wrap disconnect to remove from set
        const originalDisconnect = observer.disconnect.bind(observer);
        observer.disconnect = function() {
            observers.delete(observer);
            return originalDisconnect();
        };
        
        return observer;
    };
    window.IntersectionObserver.prototype = originalIntersectionObserver.prototype;

    // Clean up on page unload
    window.addEventListener('beforeunload', () => {
        observers.forEach(obs => {
            try { obs.disconnect(); } catch(e) {}
        });
        console.log('[PerfFix] Cleaned up', observers.size, 'observers');
    });

    // ============================================
    // FIX 3: Limit animation frame rate when idle
    // ============================================
    
    let lastInteractionTime = Date.now();
    const IDLE_THRESHOLD = 60000; // 1 minute
    
    ['click', 'scroll', 'keydown', 'mousemove', 'touchstart'].forEach(event => {
        document.addEventListener(event, () => {
            lastInteractionTime = Date.now();
        }, { passive: true });
    });

    // Check idle state periodically
    setInterval(() => {
        const isIdle = Date.now() - lastInteractionTime > IDLE_THRESHOLD;
        
        if (isIdle && !animationsPaused) {
            pauseAllAnimations();
            console.log('[PerfFix] User idle, paused animations');
        }
    }, 30000);

    // ============================================
    // FIX 4: Force GPU layer cleanup
    // ============================================
    
    function forceGPUCleanup() {
        // Force browser to release GPU memory by toggling will-change
        const cards = document.querySelectorAll('.article-card');
        cards.forEach(card => {
            card.style.willChange = 'auto';
        });
        
        // Request an animation frame to ensure changes are applied
        requestAnimationFrame(() => {
            cards.forEach(card => {
                card.style.willChange = '';
            });
        });
    }

    // Run GPU cleanup every 5 minutes
    setInterval(forceGPUCleanup, 5 * 60 * 1000);

    // ============================================
    // FIX 5: Clean up detached DOM nodes
    // ============================================
    
    function cleanupDetachedNodes() {
        // Clear any references to detached nodes in window.state
        if (window.state) {
            // Only keep essential data, clear any DOM references
            const essentialKeys = [
                'allArticles', 'filteredArticles', 'trendingTopics', 
                'storyClusters', 'filters', 'currentPage', 'totalPages'
            ];
            
            Object.keys(window.state).forEach(key => {
                if (!essentialKeys.includes(key) && 
                    window.state[key] instanceof Element) {
                    window.state[key] = null;
                }
            });
        }
    }

    // Run cleanup every 2 minutes
    setInterval(cleanupDetachedNodes, 2 * 60 * 1000);

    // ============================================
    // FIX 6: Stop .freshness-dot animation after load
    // ============================================
    
    // The freshness dot doesn't need to animate forever
    setTimeout(() => {
        const freshnesssDots = document.querySelectorAll('.freshness-dot');
        freshnesssDots.forEach(dot => {
            dot.style.animation = 'none';
            dot.style.opacity = '1';
        });
        console.log('[PerfFix] Stopped', freshnesssDots.length, 'freshness dot animations');
    }, 10000); // Stop after 10 seconds

    // ============================================
    // DIAGNOSTIC: Memory monitoring
    // ============================================
    
    if (performance.memory) {
        let lastMemory = performance.memory.usedJSHeapSize;
        let consecutiveGrowth = 0;
        
        setInterval(() => {
            const currentMemory = performance.memory.usedJSHeapSize;
            const growth = currentMemory - lastMemory;
            const growthMB = growth / 1024 / 1024;
            
            if (growthMB > 5) {
                consecutiveGrowth++;
                console.warn('[PerfFix] Memory grew by', growthMB.toFixed(2), 'MB');
                
                if (consecutiveGrowth >= 3) {
                    console.warn('[PerfFix] Significant memory leak detected, forcing cleanup');
                    forceGPUCleanup();
                    cleanupDetachedNodes();
                    consecutiveGrowth = 0;
                }
            } else {
                consecutiveGrowth = 0;
            }
            
            lastMemory = currentMemory;
        }, 60000); // Check every minute
    }

    console.log('[PerfFix] Performance fixes loaded successfully');

})();
