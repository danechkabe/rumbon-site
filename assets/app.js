'use strict';
document.addEventListener('DOMContentLoaded', () => {
  const galleryData = document.getElementById('gallery-data');
  if (galleryData) {
    const photos = JSON.parse(galleryData.textContent);
    const dialog = document.getElementById('gallery-dialog');
    const image = document.getElementById('gallery-image');
    const counter = document.getElementById('gallery-counter');
    let current = 0;
    let opener = null;
    const show = (index) => {
      current = (index + photos.length) % photos.length;
      image.src = photos[current];
      image.alt = `${document.title} · ${current + 1} / ${photos.length}`;
      counter.textContent = `${current + 1} / ${photos.length}`;
    };
    document.querySelectorAll('[data-gallery-index]').forEach((tile) => tile.addEventListener('click', () => {
      opener = tile;
      show(Number(tile.dataset.galleryIndex));
      dialog.showModal();
    }));
    dialog.querySelector('[data-gallery-prev]').addEventListener('click', () => show(current - 1));
    dialog.querySelector('[data-gallery-next]').addEventListener('click', () => show(current + 1));
    dialog.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowRight') show(current + 1);
      if (event.key === 'ArrowLeft') show(current - 1);
    });
    dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); });
    dialog.addEventListener('close', () => opener?.focus());
  }

  const dataEl = document.getElementById('map-data');
  if (!dataEl) return;
  const { groups, labels: t } = JSON.parse(dataEl.textContent);
  const status = document.getElementById('map-status');
  if (!window.L) { status.textContent = t.mapUnavailable; return; }
  // This is a city overview, never a room location. Markers use only supplied coordinates.
  const map = L.map('room-map', { scrollWheelZoom: false, tap: true }).setView([38.7223, -9.1393], 13);
  const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);
  let tileErrors = 0;
  tiles.on('tileerror', () => { if (++tileErrors > 2) status.textContent = t.mapUnavailable; });
  const bounds = [];
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  };
  groups.forEach((group) => {
    if (!group.rooms.length) return;
    let index = 0;
    const container = el('div', 'popup-room');
    const draw = () => {
      container.replaceChildren();
      const room = group.rooms[index];
      if (room.photo) {
        const image = el('img'); image.src = room.photo; image.alt = room.title; container.append(image);
      } else container.append(el('div', 'popup-placeholder', t.photo));
      container.append(el('p', '', `${t.roomLabel} ${room.index} ${t.of} ${room.total} · ${room.name}`));
      container.append(el('h3', '', room.title));
      container.append(el('p', '', room.status));
      container.append(el('p', '', `${room.price} ${t.month}`));
      const link = el('a', '', `${t.details} ↗`); link.href = room.url; container.append(link);
      if (group.rooms.length > 1) {
        const controls = el('div', 'popup-controls');
        const prev = el('button', '', '←'); prev.type = 'button'; prev.setAttribute('aria-label', t.previous);
        const next = el('button', '', '→'); next.type = 'button'; next.setAttribute('aria-label', t.next);
        prev.addEventListener('click', () => { index = (index - 1 + group.rooms.length) % group.rooms.length; draw(); });
        next.addEventListener('click', () => { index = (index + 1) % group.rooms.length; draw(); });
        controls.append(prev, el('span', '', `${index + 1} / ${group.rooms.length}`), next);
        container.append(controls);
      }
    };
    draw();
    const icon = L.divIcon({className:'price-marker',html:group.rooms[0].price,iconSize:[72,34],iconAnchor:[36,17]});
    L.marker([group.lat, group.lng], {icon, keyboard:true, alt:group.rooms[0].title}).addTo(map).bindPopup(container);
    bounds.push([group.lat, group.lng]);
  });
  if (bounds.length === 1) map.setView(bounds[0], 15);
  else if (bounds.length > 1) map.fitBounds(bounds, {padding:[50,50], maxZoom:16});
});
