document.addEventListener("DOMContentLoaded", function () {
  var guideList = document.getElementById("guide-list");
  var toggleBtn = document.getElementById("toggle-edit-mode");
  var editMode = false;
  var sortable = null;

  // Allow 400 responses to swap (rename validation errors).
  document.body.addEventListener("htmx:beforeSwap", function (event) {
    var status = event.detail.xhr.status;
    if (status === 400) {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
    }
  });

  // After htmx swaps in a new element, re-apply edit mode visibility.
  document.body.addEventListener("htmx:afterSwap", function () {
    if (editMode && guideList) {
      applyEditMode(true);
    }
  });

  function applyEditMode(on) {
    if (!guideList) return;
    guideList.querySelectorAll(".drag-handle").forEach(function (el) {
      el.classList.toggle("d-none", !on);
    });
    guideList.querySelectorAll(".guide-edit-actions").forEach(function (el) {
      el.classList.toggle("d-none", !on);
    });
  }

  function setEditMode(on) {
    editMode = on;
    if (toggleBtn) toggleBtn.textContent = on ? "Done" : "Edit";
    applyEditMode(on);

    if (on && guideList && !sortable) {
      sortable = new Sortable(guideList, {
        handle: ".drag-handle",
        animation: 150,
        onEnd: function () {
          htmx.trigger(guideList, "end");
        },
      });
    } else if (!on && sortable) {
      sortable.destroy();
      sortable = null;
    }
  }

  if (toggleBtn) {
    toggleBtn.addEventListener("click", function () {
      setEditMode(!editMode);
    });
  }
});
