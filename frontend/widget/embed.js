/* Embeds the website chat. Messages are stored for a person to review. */
(function () {
  var script = document.currentScript;
  if (!script) return;
  var channel = script.getAttribute("data-channel");
  var token = script.getAttribute("data-token");
  var origin = script.getAttribute("data-origin") || "";
  if (!channel || !token) return;
  var frame = document.createElement("iframe");
  frame.title = "Chat";
  frame.src =
    origin +
    "/widget?channel=" +
    encodeURIComponent(channel) +
    "&token=" +
    encodeURIComponent(token);
  frame.style.cssText =
    "position:fixed;right:16px;bottom:16px;width:360px;height:520px;border:0;border-radius:16px;box-shadow:0 8px 30px rgba(15,23,42,.16);z-index:2147483000;background:#fff";
  document.body.appendChild(frame);
})();
