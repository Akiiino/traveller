document.addEventListener("DOMContentLoaded", function () {
  // htmx 1.x ignores 4xx responses by default. Both the conflict path (409)
  // and the per-field validation path (400) return a rendered edit form
  // populated with the user's typed values — we want it swapped in just
  // like a 200 would be.
  document.body.addEventListener("htmx:beforeSwap", function (event) {
    const status = event.detail.xhr.status;
    if (status === 409 || status === 400) {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
    }
  });

  // Client-side HTML5 validation for the edit form. The edit "form" is not
  // wrapped in a <form> element (the desktop layout is a <tr>), so htmx
  // skips the normal validation pass. Without this, a partially-filled
  // datetime-local input submits an empty string and silently clears the
  // on-disk timestamp; a malformed coordinate trips the `pattern` attribute
  // but is also submitted anyway. Server-side validation catches non-empty
  // bad input, but can't tell "user cleared the field" from "browser
  // dropped a partial value" — only the browser knows.
  document.body.addEventListener("htmx:beforeRequest", function (event) {
    if (event.detail.requestConfig.verb === "get") return;
    const trigger = event.detail.elt;
    const container = trigger && trigger.closest(".editing");
    if (!container) return;

    let firstInvalid = null;
    container.querySelectorAll("input, textarea, select").forEach((input) => {
      if (input.checkValidity()) {
        input.classList.remove("field-error");
      } else {
        input.classList.add("field-error");
        if (firstInvalid === null) firstInvalid = input;
      }
    });
    if (firstInvalid) {
      firstInvalid.reportValidity();
      event.preventDefault();
    }
  });

  const savedTab = localStorage.getItem("selectedTab");
  const guideId = document.body.dataset.guideId;
  if (!guideId) {
    return; // Index page; no map.
  }
  const geojsonUrl = `/api/guide/${guideId}/points_geojson`;

  // Update the map button click handler
  document.addEventListener("click", function (e) {
    const mapButton = e.target.closest(".btn-show-on-map");
    if (mapButton) {
      // Get the point ID from data attribute
      const id = mapButton.dataset.id;
      if (!id) {
        console.error("Missing data-id on map button");
        return;
      }

      // Switch to map tab
      const mapTab = document.querySelector(
        '.view-tab[data-target="map-container"]',
      );
      mapTab.click();

      // Give the map a moment to initialize properly after tab switch
      setTimeout(() => {
        if (markers[id]) {
          markers[id].openPopup();
          map.setView(markers[id].getLatLng(), 15);
        } else {
          console.warn(`No marker found for ID: ${id}`);
        }
      }, 300);
    }
  });
  const map = L.map("map").setView([37.5665, 126.978], 10);

  L.tileLayer("https://{s}.tile.openstreetmap.de/{z}/{x}/{y}.png", {
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    language: "en",
  }).addTo(map);

  // Pins are tinted on the fly from each category's editable hex color
  // (carried in the GeoJSON feature's `color` property). Falls back to this
  // default — matching the /types add-form default — when a category has no
  // color or an unknown/malformed one.
  const DEFAULT_PIN_COLOR = "#1010a0";

  function pinSvg(color) {
    return (
      `<svg xmlns="http://www.w3.org/2000/svg" width="25" height="41" viewBox="0 0 25 41">` +
      `<path d="M12.5 0C5.6 0 0 5.6 0 12.5 0 21.5 12.5 41 12.5 41S25 21.5 25 12.5C25 5.6 19.4 0 12.5 0z" ` +
      `fill="${color}" stroke="#ffffff" stroke-width="1.2"/>` +
      `<circle cx="12.5" cy="12.5" r="5" fill="#ffffff"/></svg>`
    );
  }

  // Function to create a colored icon from a category's hex color
  function createColoredIcon(color) {
    const c =
      color && /^#[0-9a-fA-F]{3,8}$/.test(color) ? color : DEFAULT_PIN_COLOR;
    return new L.Icon({
      iconUrl: "data:image/svg+xml," + encodeURIComponent(pinSvg(c)),
      shadowUrl: "/vendor/marker-icons/marker-shadow.png",
      iconSize: [25, 41],
      iconAnchor: [12, 41],
      popupAnchor: [1, -34],
      shadowSize: [41, 41],
    });
  }

  const markers = {};
  const markerData = {}; // Store marker data for filtering
  const markerGroup = L.featureGroup().addTo(map);

  function highlightCard(id) {
    const card = document.querySelector(`.poi-card[data-id="${id}"]`);
    if (!card) return;
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    card.classList.add("highlight-element");
    setTimeout(() => card.classList.remove("highlight-element"), 2000);
  }

  function jumpToDetails(id) {
    // On narrow viewports the list lives behind the "List View" tab, so
    // switch to it first and let the DOM settle before highlighting.
    if (window.innerWidth < 992) {
      document
        .querySelector('.view-tab[data-target="table-container"]')
        .click();
      setTimeout(() => highlightCard(id), 300);
    } else {
      highlightCard(id);
    }
  }
  function loadPOIs() {
    fetch(geojsonUrl)
      .then((response) => response.json())
      .then((data) => {
        markerGroup.clearLayers();

        data.features.forEach((feature) => {
          const props = feature.properties;
          const coords = feature.geometry.coordinates;

          if (coords[0] === 0 && coords[1] === 0) {
            console.log(
              `Skipping point "${props.name}" with coordinates (0, 0)`,
            );
            return;
          }

          const latlng = L.latLng(coords[1], coords[0]);

          // Create marker with colored icon based on category
          const marker = L.marker(latlng, {
            title: props.name,
            opacity: props.visited ? 0.6 : 1.0,
            icon: createColoredIcon(props.color),
          });

          // Build the popup as DOM nodes with textContent rather than
          // innerHTML — a POI named `<img src=x onerror=…>` would
          // otherwise fire on page load, before the user even opens
          // the popup.
          const popupContent = document.createElement("div");

          const heading = document.createElement("h5");
          heading.textContent = props.name || "Unnamed Point";
          popupContent.appendChild(heading);

          const desc = document.createElement("p");
          desc.textContent = props.description || "";
          popupContent.appendChild(desc);

          const cat = document.createElement("p");
          cat.textContent = `Category: ${props.category || "None"}`;
          popupContent.appendChild(cat);

          if (props.link) {
            const linkP = document.createElement("p");
            const a = document.createElement("a");
            a.href = props.link;
            a.target = "_blank";
            a.textContent = "Link";
            linkP.appendChild(a);
            popupContent.appendChild(linkP);
          }

          if (props.timestamp) {
            const dateP = document.createElement("p");
            dateP.textContent = `Date: ${new Date(props.timestamp).toLocaleDateString()}`;
            popupContent.appendChild(dateP);
          }

          const btnWrap = document.createElement("div");
          btnWrap.className = "text-center mt-2";
          const detailsBtn = document.createElement("button");
          detailsBtn.className = "btn btn-sm btn-primary jump-to-details";
          detailsBtn.dataset.id = props.id;
          detailsBtn.textContent = "View Details";
          detailsBtn.addEventListener("click", function () {
            jumpToDetails(this.dataset.id);
          });
          btnWrap.appendChild(detailsBtn);
          popupContent.appendChild(btnWrap);

          marker.bindPopup(popupContent);

          // Store marker and its data
          markers[props.id] = marker;
          markerData[props.id] = props;

          // Add to marker group only if it passes the current filters
          const showVisited = document.getElementById("show-visited").checked;
          const dateFilter = document.getElementById("date-filter")?.value;

          if (shouldShowMarker(props, showVisited, dateFilter)) {
            markerGroup.addLayer(marker);
          }
        });

        if (markerGroup.getLayers().length > 0) {
          map.fitBounds(markerGroup.getBounds(), { padding: [50, 50] });
        }
      })
      .catch((error) => console.error("Error loading POIs:", error));
  }

  // Function to determine if a marker should be shown based on filters
  function shouldShowMarker(point, showVisited, dateFilter) {
    // Handle visited filter
    if (point.visited && !showVisited) {
      return false;
    }

    // Handle date filter if it exists
    if (dateFilter) {
      // Convert both dates to YYYY-MM-DD format for comparison
      const filterDate = dateFilter.split("T")[0];
      const pointDate = point.timestamp ? point.timestamp.split("T")[0] : null;

      if (!pointDate || pointDate !== filterDate) {
        return false;
      }
    }

    return true;
  }

  // Function to apply filters
  function applyFilters() {
    const showVisited = document.getElementById("show-visited").checked;
    const dateFilter = document.getElementById("date-filter")?.value;

    Object.entries(markers).forEach(([id, marker]) => {
      const point = markerData[id];

      if (shouldShowMarker(point, showVisited, dateFilter)) {
        markerGroup.addLayer(marker);
      } else {
        markerGroup.removeLayer(marker);
      }
    });

    // Update clear date filter button visibility
    if (document.getElementById("clear-date-filter")) {
      document.getElementById("clear-date-filter").style.display = dateFilter
        ? "inline-block"
        : "none";
    }
  }

  // Add date filter UI after the map is loaded
  function addDateFilterUI() {
    const controlsDiv = document.querySelector("#map-container .mb-3");

    // Create date filter elements
    const dateFilterContainer = document.createElement("div");
    dateFilterContainer.className = "date-filter-container mt-2";
    dateFilterContainer.innerHTML = `
      <label for="date-filter">Filter by date:</label>
      <div class="d-flex align-items-center">
        <input type="date" id="date-filter" class="form-control form-control-sm">
        <button id="clear-date-filter" class="btn btn-sm btn-secondary ms-2" style="display: none;">Clear</button>
      </div>
    `;

    controlsDiv.appendChild(dateFilterContainer);

    // Add event listeners
    document
      .getElementById("date-filter")
      .addEventListener("change", function () {
        applyFilters();
        // Show clear button when a date is selected
        document.getElementById("clear-date-filter").style.display = this.value
          ? "inline-block"
          : "none";
      });

    document
      .getElementById("clear-date-filter")
      .addEventListener("click", function () {
        document.getElementById("date-filter").value = "";
        applyFilters();
        this.style.display = "none";
      });
  }

  // Initialize
  loadPOIs();
  addDateFilterUI();

  document.getElementById("fit-bounds").addEventListener("click", function () {
    if (markerGroup.getLayers().length > 0) {
      map.fitBounds(markerGroup.getBounds(), { padding: [50, 50] });
    }
  });

  document
    .getElementById("show-visited")
    .addEventListener("change", function () {
      applyFilters();
    });

  // Reinitialize event listeners when DOM updates
  document.body.addEventListener("htmx:afterSwap", function (event) {
    loadPOIs();
    htmx.process(event.detail.target);
  });

  document.body.addEventListener("htmx:afterOnLoad", function () {
    loadPOIs();
  });

  // Handle marker popups that were created dynamically
  document.body.addEventListener("click", function (e) {
    if (e.target.classList.contains("jump-to-details")) {
      const pointId = e.target.getAttribute("data-id");
      jumpToDetails(pointId);
    }
  });

  const viewTabs = document.querySelectorAll(".view-tab");
  viewTabs.forEach((tab) => {
    tab.addEventListener("click", function () {
      viewTabs.forEach((t) => t.classList.remove("active"));

      this.classList.add("active");

      document.getElementById("map-container").style.display = "none";
      document.getElementById("table-container").style.display = "none";

      const targetId = this.getAttribute("data-target");
      document.getElementById(targetId).style.display = "block";

      localStorage.setItem("selectedTab", targetId);

      if (targetId === "map-container") {
        map.invalidateSize();
      }
    });
  });

  if (savedTab && document.getElementById(savedTab)) {
    document.querySelector(`.view-tab[data-target="${savedTab}"]`).click();
  } else {
    document.querySelector('.view-tab[data-target="map-container"]').click();
  }

  const fullscreenToggle = document.getElementById("fullscreen-toggle");
  const mapContainer = document.getElementById("map-container");

  fullscreenToggle.addEventListener("click", function () {
    mapContainer.classList.toggle("map-fullscreen");

    if (mapContainer.classList.contains("map-fullscreen")) {
      fullscreenToggle.textContent = "×";
    } else {
      fullscreenToggle.textContent = "⛶";
    }

    setTimeout(() => {
      map.invalidateSize();
    }, 100);
  });
});
