(function () {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socketUrl = protocol + "://" + window.location.host + "/ws/admin";
    let fallbackTimer = null;

    function startFallbackPolling() {
        if (fallbackTimer) {
            return;
        }

        fallbackTimer = window.setInterval(function () {
            window.location.reload();
        }, 5000);
    }

    try {
        const socket = new WebSocket(socketUrl);

        socket.addEventListener("message", function () {
            window.location.reload();
        });

        socket.addEventListener("error", startFallbackPolling);
        socket.addEventListener("close", startFallbackPolling);
    } catch (error) {
        startFallbackPolling();
    }
}());
