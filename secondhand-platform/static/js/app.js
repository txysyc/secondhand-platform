(function () {
    function ready(callback) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", callback);
        } else {
            callback();
        }
    }

    function getContentField(form) {
        return form.querySelector("textarea[name='content']");
    }

    function updateSubmitState(form) {
        var field = getContentField(form);
        var submit = form.querySelector("button[type='submit']");
        if (!field || !submit) {
            return;
        }
        submit.disabled = field.value.trim().length === 0;
    }

    function setupEmptySubmitGuards() {
        document.querySelectorAll("form[data-disable-empty-submit]").forEach(function (form) {
            var field = getContentField(form);
            if (!field) {
                return;
            }
            updateSubmitState(form);
            field.addEventListener("input", function () {
                updateSubmitState(form);
            });
        });
    }

    function resizeTextarea(field) {
        var minHeight = 46;
        var maxHeight = field.closest(".comment-reply-form") ? 180 : 220;
        field.style.height = minHeight + "px";
        field.style.height = Math.min(maxHeight, Math.max(minHeight, field.scrollHeight)) + "px";
    }

    function setupAutoExpandTextareas() {
        document.querySelectorAll(".comment-composer textarea, .comment-reply-form textarea").forEach(function (field) {
            field.rows = 1;
            resizeTextarea(field);
            field.addEventListener("input", function () {
                resizeTextarea(field);
            });
        });
    }

    function setupGallerySwitcher() {
        document.querySelectorAll("[data-gallery]").forEach(function (gallery) {
            var main = gallery.querySelector("[data-gallery-main]");
            if (!main) {
                return;
            }

            gallery.querySelectorAll("[data-gallery-thumb]").forEach(function (thumb) {
                thumb.addEventListener("click", function () {
                    main.src = thumb.getAttribute("data-gallery-thumb");
                    main.alt = thumb.getAttribute("data-gallery-alt") || main.alt;
                    gallery.querySelectorAll("[data-gallery-thumb]").forEach(function (item) {
                        item.classList.toggle("is-active", item === thumb);
                    });
                });
            });
        });
    }

    function setupReplyDisclosure() {
        document.querySelectorAll("[data-reply-toggle]").forEach(function (toggle) {
            var targetId = toggle.getAttribute("data-reply-toggle");
            var form = document.getElementById(targetId);
            if (!form) {
                return;
            }
            toggle.addEventListener("click", function () {
                var shouldOpen = form.hidden;
                document.querySelectorAll(".comment-reply-form").forEach(function (item) {
                    if (item !== form) {
                        item.hidden = true;
                        var otherToggle = document.querySelector("[data-reply-toggle='" + item.id + "']");
                        if (otherToggle) {
                            otherToggle.setAttribute("aria-expanded", "false");
                        }
                    }
                });
                form.hidden = !shouldOpen;
                toggle.setAttribute("aria-expanded", String(shouldOpen));
                if (shouldOpen) {
                    var field = getContentField(form);
                    if (field) {
                        field.focus();
                    }
                    form.scrollIntoView({ block: "nearest", behavior: "smooth" });
                }
            });
        });

        document.querySelectorAll("[data-reply-cancel]").forEach(function (button) {
            button.addEventListener("click", function () {
                var form = button.closest(".comment-reply-form");
                if (!form) {
                    return;
                }
                form.hidden = true;
                var toggle = document.querySelector("[data-reply-toggle='" + form.id + "']");
                if (toggle) {
                    toggle.setAttribute("aria-expanded", "false");
                    toggle.focus();
                }
            });
        });
    }

    function scrollMessagesToBottom(list) {
        if (list) {
            list.scrollTop = list.scrollHeight;
        }
    }

    function formatMessageTime(value) {
        return new Date(value).toLocaleString("zh-CN", {
            hour12: false,
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit"
        });
    }

    function appendMessage(list, message, currentUserId) {
        var empty = document.getElementById("message-empty");
        if (empty) {
            empty.remove();
        }

        var item = document.createElement("li");
        item.className = "message-item" + (message.sender_id === currentUserId ? " is-mine" : "");

        var bubble = document.createElement("div");
        bubble.className = "message-bubble";

        var body = document.createElement("p");
        body.className = "message-content";
        body.textContent = message.content;
        bubble.appendChild(body);

        var meta = document.createElement("div");
        meta.className = "message-meta";

        var name = document.createElement("strong");
        name.textContent = message.sender_display_name;

        var time = document.createElement("span");
        time.textContent = formatMessageTime(message.created_at);

        meta.appendChild(name);
        meta.appendChild(time);
        item.appendChild(bubble);
        item.appendChild(meta);
        list.appendChild(item);
        scrollMessagesToBottom(list);
    }

    function setupMessaging() {
        var form = document.getElementById("message-form");
        var list = document.getElementById("message-list");
        if (!form || !list) {
            return;
        }

        scrollMessagesToBottom(list);

        var field = getContentField(form);
        var error = document.getElementById("message-error");
        var status = document.getElementById("message-send-status");
        var currentUserId = Number(form.getAttribute("data-current-user-id"));
        var websocketUrl = form.getAttribute("data-websocket-url");
        var socket = null;

        function setStatus(text) {
            if (status) {
                status.textContent = text;
            }
        }

        if (websocketUrl && window.WebSocket) {
            try {
                socket = new WebSocket(websocketUrl);
                socket.addEventListener("open", function () {
                    setStatus("实时连接已建立");
                });
                socket.addEventListener("close", function () {
                    setStatus("实时连接不可用，将使用普通发送");
                });
                socket.addEventListener("error", function () {
                    setStatus("实时连接异常，将使用普通发送");
                });
                socket.addEventListener("message", function (event) {
                    var payload = JSON.parse(event.data);
                    if (payload.type === "message") {
                        if (error) {
                            error.hidden = true;
                        }
                        appendMessage(list, payload.message, currentUserId);
                    }
                    if (payload.type === "error" && error) {
                        error.textContent = payload.message;
                        error.hidden = false;
                    }
                });
            } catch (err) {
                setStatus("实时连接不可用，将使用普通发送");
            }
        }

        form.addEventListener("submit", function (event) {
            if (!socket || socket.readyState !== WebSocket.OPEN) {
                return;
            }

            event.preventDefault();
            var content = field.value.trim();
            if (!content) {
                if (error) {
                    error.textContent = "消息内容不能为空";
                    error.hidden = false;
                }
                return;
            }

            socket.send(JSON.stringify({ content: content }));
            field.value = "";
            resizeTextarea(field);
            updateSubmitState(form);
        });
    }

    ready(function () {
        setupEmptySubmitGuards();
        setupAutoExpandTextareas();
        setupGallerySwitcher();
        setupReplyDisclosure();
        setupMessaging();
    });
})();
