/* BUILD LOOP mini-game. Pure client-side: no backend, no data collection.
   Run the seven stages in order. Wrong move resets the run. */
(function () {
    var STAGES = ["Problem", "Understand", "Build", "Test", "Break", "Debug", "Rebuild"];
    var modal = document.querySelector("[data-game]");
    if (!modal) {
        return;
    }
    var startPane = modal.querySelector("[data-game-start]");
    var boardPane = modal.querySelector("[data-game-board]");
    var endPane = modal.querySelector("[data-game-end]");
    var targets = modal.querySelector("[data-game-targets]");
    var message = modal.querySelector("[data-game-message]");
    var progressLabel = modal.querySelector("[data-game-progress]");
    var statusLabel = modal.querySelector("[data-game-status]");
    var token = modal.querySelector("[data-game-token]");
    var progress = 0;
    var lastOpener = null;

    function show(pane) {
        [startPane, boardPane, endPane].forEach(function (el) {
            el.hidden = el !== pane;
        });
    }

    function shuffle(items) {
        for (var i = items.length - 1; i > 0; i--) {
            var j = Math.floor(Math.random() * (i + 1));
            var tmp = items[i];
            items[i] = items[j];
            items[j] = tmp;
        }
        return items;
    }

    function render() {
        progressLabel.textContent = progress + "/" + STAGES.length;
        token.style.transform = "translateX(" + progress * 26 + "px)";
    }

    function startRun() {
        progress = 0;
        statusLabel.textContent = "Status: active";
        message.textContent = "Click the stages in build order.";
        message.classList.remove("game-error");
        targets.textContent = "";
        shuffle(STAGES.slice()).forEach(function (stage) {
            var item = document.createElement("li");
            var button = document.createElement("button");
            button.type = "button";
            button.textContent = stage;
            button.addEventListener("click", function () {
                pick(stage);
            });
            item.appendChild(button);
            targets.appendChild(item);
        });
        render();
        show(boardPane);
        var first = targets.querySelector("button");
        if (first) {
            first.focus();
        }
    }

    function pick(stage) {
        if (stage === STAGES[progress]) {
            progress += 1;
            message.textContent = stage + " — stable.";
            message.classList.remove("game-error");
            render();
            if (progress === STAGES.length) {
                statusLabel.textContent = "Status: rebuilt";
                show(endPane);
                var replay = modal.querySelector("[data-game-replay]");
                if (replay) {
                    replay.focus();
                }
            }
        } else {
            progress = 0;
            message.textContent = "System error on '" + stage + "' — try again from Problem.";
            message.classList.add("game-error");
            render();
        }
    }

    function openGame(opener) {
        lastOpener = opener || null;
        show(startPane);
        modal.hidden = false;
        var play = modal.querySelector("[data-game-play]");
        if (play) {
            play.focus();
        }
    }

    function closeGame() {
        modal.hidden = true;
        if (lastOpener && lastOpener.focus) {
            lastOpener.focus();
        }
    }

    document.querySelectorAll("[data-game-open]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            openGame(btn);
        });
    });
    modal.querySelector("[data-game-play]").addEventListener("click", startRun);
    modal.querySelector("[data-game-replay]").addEventListener("click", startRun);
    modal.querySelectorAll("[data-game-close]").forEach(function (btn) {
        btn.addEventListener("click", closeGame);
    });
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && !modal.hidden) {
            closeGame();
        }
    });
})();
