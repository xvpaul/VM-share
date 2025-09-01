// Palettes
// FF6B6B
// 52357B
// 210F37
// FFB200
// FFD93D
// 5CB338

particlesJS("particles-js", {
    particles: {
        number: {
            value: 5,
            density: {
                enable: true,
                value_area: 800
            }
        },
        color: {
            value: "#FFB200"
        },
        shape: {
            type: "circle",
            stroke: {
                width: 0,
                color: "#FFB200"
            },
            polygon: {
                nb_sides: 5
            },
            image: {
                src: "img/github.svg",
                width: 100,
                height: 100
            }
        },
        opacity: {
            value: 1,
            random: false,
            anim: {
                enable: false,
                speed: 1,
                opacity_min: 0.1,
                sync: false
            }
        },
        size: {
            value: 2,
            random: false,
            anim: {
                enable: false,
                speed: 40,
                size_min: 0.1,
                sync: false
            }
        },
        line_linked: {
            enable: true,
            distance: 200,
            color: "#FFB200",
            opacity: 1,
            width: 1
        },
        move: {
            enable: true,
            speed: 5,
            direction: "none",
            random: false,
            straight: false,
            out_mode: "out",
            bounce: false,
            attract: {
                enable: false,
                rotateX: 600,
                rotateY: 1200
            }
        }
    },
    interactivity: {
    detect_on: "window",              // <-- was "canvas"
    events: {
      onhover: { enable: true, mode: "repulse" },
      onclick: { enable: true, mode: "push" },
      resize: true
    },
    modes: {
      repulse: { distance: 100, duration: 0.5 },
      push: { particles_nb: 2 },
      // keep your other modes if any
    }
  },
  retina_detect: true
});
