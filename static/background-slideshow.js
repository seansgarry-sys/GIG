(function () {
    const slideshowRoots = document.querySelectorAll("[data-slideshow]");

    slideshowRoots.forEach(function (root) {
        const raw = root.getAttribute("data-slideshow");
        if (!raw) {
            return;
        }

        let images;
        try {
            images = JSON.parse(raw);
        } catch (error) {
            return;
        }

        if (!Array.isArray(images) || !images.length) {
            return;
        }

        let currentIndex = 0;
        root.style.setProperty("--hero-image", 'url("' + images[currentIndex] + '")');

        if (images.length < 2) {
            return;
        }

        window.setInterval(function () {
            currentIndex = (currentIndex + 1) % images.length;
            root.style.setProperty("--hero-image", 'url("' + images[currentIndex] + '")');
        }, 5500);
    });
}());
