document.addEventListener('DOMContentLoaded', function() {
  const savedTab = localStorage.getItem('selectedTab');
  
  document.addEventListener('click', function(e) {
    if (e.target.closest('.btn-show-on-map')) {
      const id = e.target.closest('.btn-show-on-map').dataset.id;
      const mapTab = document.querySelector('.view-tab[data-target="map-container"]');
      mapTab.click();
      
      if (markers[id]) {
        markers[id].openPopup();
        map.setView(markers[id].getLatLng(), 15);
      }
    }
  });
  
  const map = L.map('map').setView([37.5665, 126.9780], 10);
  
  L.tileLayer('https://{s}.tile.openstreetmap.de/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    language: 'en'
  }).addTo(map);
  
  // Category to color mapping based on the colors defined in init.py
  const categoryColors = {
    'See': 'green',
    'Sleep': 'gold',
    'Do': 'orange',
    'Drink': 'red',
    'Go': 'blue',
    'Eat': 'red',
    'Buy': 'violet',
    'default': 'blue'
  };

  // Function to create colored icon based on category
  function createColoredIcon(category) {
    const color = categoryColors[category] || categoryColors['default'];
    return new L.Icon({
      iconUrl: `https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-${color}.png`,
      shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
      iconSize: [25, 41],
      iconAnchor: [12, 41],
      popupAnchor: [1, -34],
      shadowSize: [41, 41]
    });
  }
  
  const markers = {};
  const markerData = {}; // Store marker data for filtering
  const markerGroup = L.featureGroup().addTo(map);
  
  function attachRowHoverEvents(rowElement, markerId) {
    if (!rowElement || !markers[markerId]) return;
    
    rowElement.addEventListener('mouseenter', () => {
      markers[markerId].setZIndexOffset(1000);
      markers[markerId].openPopup();
    });
    
    rowElement.addEventListener('mouseleave', () => {
      markers[markerId].setZIndexOffset(0);
      markers[markerId].closePopup();
    });
  }
  
  // Function to jump to card/table row from the map
  function jumpToDetails(id) {
    // Check if we're on mobile
    const isMobile = window.innerWidth < 992;
    
    if (isMobile) {
      // On mobile, switch to list view tab first
      const listTab = document.querySelector('.view-tab[data-target="table-container"]');
      listTab.click();
    }
    
    // Find the corresponding element based on the view
    let targetElement;
    if (document.querySelector('.desktop-view').style.display !== 'none') {
      // Desktop view - find table row
      targetElement = document.querySelector(`tr[data-id="${id}"]`);
    } else {
      // Mobile view - find card
      targetElement = document.querySelector(`.poi-card[data-id="${id}"]`);
    }
    
    if (targetElement) {
      // Scroll the element into view
      targetElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
      
      // Add a highlight effect
      targetElement.classList.add('highlight-element');
      setTimeout(() => {
        targetElement.classList.remove('highlight-element');
      }, 2000);
    }
  }
  
  function loadPOIs() {
    fetch('/api/points_geojson')
      .then(response => response.json())
      .then(data => {
        markerGroup.clearLayers();
        
        data.features.forEach(feature => {
          const props = feature.properties;
          const coords = feature.geometry.coordinates;
          
          if (coords[0] === 0 && coords[1] === 0) {
            console.log(`Skipping point "${props.name}" with coordinates (0, 0)`);
            return;
          }
          
          const latlng = L.latLng(coords[1], coords[0]);
          
          // Create marker with colored icon based on category
          const marker = L.marker(latlng, {
            title: props.name,
            opacity: props.visited ? 0.6 : 1.0,
            icon: createColoredIcon(props.category)
          });
          
          const popupContent = document.createElement('div');
          popupContent.innerHTML = `
            <h5>${props.name || 'Unnamed Point'}</h5>
            <p>${props.description || ''}</p>
            <p>Category: ${props.category || 'None'}</p>
            ${props.link ? `<p><a href="${props.link}" target="_blank">Link</a></p>` : ''}
            ${props.timestamp ? `<p>Date: ${new Date(props.timestamp).toLocaleDateString()}</p>` : ''}
            <div class="text-center mt-2">
              <button class="btn btn-sm btn-primary jump-to-details" data-id="${props.id}">View Details</button>
            </div>
          `;
          
          // Add event listener to the button
          popupContent.querySelector('.jump-to-details').addEventListener('click', function() {
            const pointId = this.getAttribute('data-id');
            jumpToDetails(pointId);
          });
          
          marker.bindPopup(popupContent);
          
          // Store marker and its data
          markers[props.id] = marker;
          markerData[props.id] = props;
          
          // Add to marker group only if it passes the current filters
          const showVisited = document.getElementById('show-visited').checked;
          const dateFilter = document.getElementById('date-filter')?.value;
          
          if (shouldShowMarker(props, showVisited, dateFilter)) {
            markerGroup.addLayer(marker);
          }
          
          const row = document.querySelector(`tr[data-id="${props.id}"]`);
          if (row) {
            row.id = `poi-${props.id}`;
            attachRowHoverEvents(row, props.id);
          }
        });
        
        if (markerGroup.getLayers().length > 0) {
          map.fitBounds(markerGroup.getBounds(), { padding: [50, 50] });
        }
      })
      .catch(error => console.error('Error loading POIs:', error));
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
      const filterDate = dateFilter.split('T')[0];
      const pointDate = point.timestamp ? point.timestamp.split('T')[0] : null;
      
      if (!pointDate || pointDate !== filterDate) {
        return false;
      }
    }
    
    return true;
  }
  
  // Function to apply filters
  function applyFilters() {
    const showVisited = document.getElementById('show-visited').checked;
    const dateFilter = document.getElementById('date-filter')?.value;
    
    Object.entries(markers).forEach(([id, marker]) => {
      const point = markerData[id];
      
      if (shouldShowMarker(point, showVisited, dateFilter)) {
        markerGroup.addLayer(marker);
      } else {
        markerGroup.removeLayer(marker);
      }
    });
    
    // Update clear date filter button visibility
    if (document.getElementById('clear-date-filter')) {
      document.getElementById('clear-date-filter').style.display = 
        dateFilter ? 'inline-block' : 'none';
    }
  }
  
  // Add date filter UI after the map is loaded
  function addDateFilterUI() {
    const controlsDiv = document.querySelector('#map-container .mb-3');
    
    // Create date filter elements
    const dateFilterContainer = document.createElement('div');
    dateFilterContainer.className = 'date-filter-container mt-2';
    dateFilterContainer.innerHTML = `
      <label for="date-filter">Filter by date:</label>
      <div class="d-flex align-items-center">
        <input type="date" id="date-filter" class="form-control form-control-sm">
        <button id="clear-date-filter" class="btn btn-sm btn-secondary ms-2" style="display: none;">Clear</button>
      </div>
    `;
    
    controlsDiv.appendChild(dateFilterContainer);
    
    // Add event listeners
    document.getElementById('date-filter').addEventListener('change', function() {
      applyFilters();
      // Show clear button when a date is selected
      document.getElementById('clear-date-filter').style.display = 
        this.value ? 'inline-block' : 'none';
    });
    
    document.getElementById('clear-date-filter').addEventListener('click', function() {
      document.getElementById('date-filter').value = '';
      applyFilters();
      this.style.display = 'none';
    });
  }
  
  // Initialize
  loadPOIs();
  addDateFilterUI();
  
  document.getElementById('fit-bounds').addEventListener('click', function() {
    if (markerGroup.getLayers().length > 0) {
      map.fitBounds(markerGroup.getBounds(), { padding: [50, 50] });
    }
  });
  
  document.getElementById('show-visited').addEventListener('change', function() {
    applyFilters();
  });

  // Reinitialize event listeners when DOM updates
  document.body.addEventListener('htmx:afterSwap', function(event) {
    loadPOIs();
    htmx.process(event.detail.target);
  });
  
  document.body.addEventListener('htmx:afterOnLoad', function() {
    loadPOIs();
  });
  
  // Handle marker popups that were created dynamically
  document.body.addEventListener('click', function(e) {
    if (e.target.classList.contains('jump-to-details')) {
      const pointId = e.target.getAttribute('data-id');
      jumpToDetails(pointId);
    }
  });
  
  const viewTabs = document.querySelectorAll('.view-tab');
  viewTabs.forEach(tab => {
    tab.addEventListener('click', function() {
      viewTabs.forEach(t => t.classList.remove('active'));
      
      this.classList.add('active');
      
      document.getElementById('map-container').style.display = 'none';
      document.getElementById('table-container').style.display = 'none';
      
      const targetId = this.getAttribute('data-target');
      document.getElementById(targetId).style.display = 'block';
      
      localStorage.setItem('selectedTab', targetId);
      
      if (targetId === 'map-container') {
        map.invalidateSize();
      }
    });
  });
  
  if (savedTab && document.getElementById(savedTab)) {
    document.querySelector(`.view-tab[data-target="${savedTab}"]`).click();
  } else {
    document.querySelector('.view-tab[data-target="map-container"]').click();
  }
  
  const fullscreenToggle = document.getElementById('fullscreen-toggle');
  const mapContainer = document.getElementById('map-container');
  
  fullscreenToggle.addEventListener('click', function() {
    mapContainer.classList.toggle('map-fullscreen');
    
    if (mapContainer.classList.contains('map-fullscreen')) {
      fullscreenToggle.textContent = '×';
    } else {
      fullscreenToggle.textContent = '⛶';
    }
    
    setTimeout(() => {
      map.invalidateSize();
    }, 100);
  });
});
