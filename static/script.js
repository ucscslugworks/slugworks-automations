document.addEventListener('DOMContentLoaded', (event) => {
    var socket = io.connect('https://' + document.domain + ':' + location.port);

    socket.on('connect', function() {
        console.log('WebSocket connected');
    });

    socket.on('update', function(data) {
        console.log('Update received:', data.message);
        location.reload();
    });

    socket.on('disconnect', function() {
        console.log('WebSocket disconnected');
    });
});
