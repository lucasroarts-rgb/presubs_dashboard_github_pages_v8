/*
 * Updated thank-you-page tracking snippet - shares one event_id between the
 * browser pixel and the server-side CAPI call (scripts/meta_capi.py), so
 * Meta deduplicates them into a single CompleteRegistration instead of
 * counting it twice.
 *
 * REQUIRES a backend change: whatever confirms the booking/lead must
 * generate a unique id for that confirmation and append it to the
 * redirect URL that sends the visitor to this thank-you page, e.g.:
 *   https://.../obrigado-academy?eid=<uuid-or-record-id>
 * That same system then calls send_complete_registration(event_id=<that id>, ...)
 * from scripts/meta_capi.py at the moment it confirms the booking.
 *
 * If the backend cannot be changed yet, this snippet falls back to
 * generating its own id - CAPI will still work, it just will not dedupe
 * against the browser fire (Meta will count both as separate events until
 * the backend is updated to pass a shared id).
 *
 * Replace the old "Google Ads + Meta CompleteRegistration" script block on
 * the thank-you page with this one. Everything else on the page (pixel
 * base loader, Google tag loader) stays the same.
 */
(function () {
  var pixelId = '479067206740588';

  var googleStorageKey =
    'peasy_google_complete_academy_' + window.location.pathname;

  var metaStorageKey =
    'peasy_meta_complete_academy_' + window.location.pathname;

  function wasSent(key) {
    try {
      return window.sessionStorage.getItem(key) === '1';
    } catch (error) {
      return false;
    }
  }

  function markAsSent(key) {
    try {
      window.sessionStorage.setItem(key, '1');
    } catch (error) {
      // O evento continua funcionando mesmo sem sessionStorage.
    }
  }

  // Shared event id: read from the URL if the confirmation backend passed
  // one (?eid=...), otherwise generate one so the pixel call still works.
  function getEventId() {
    var params = new URLSearchParams(window.location.search);
    var fromUrl = params.get('eid');
    if (fromUrl) return fromUrl;

    if (window.crypto && window.crypto.randomUUID) {
      return window.crypto.randomUUID();
    }
    return 'evt_' + Date.now() + '_' + Math.random().toString(36).slice(2);
  }

  var eventId = getEventId();

  var googleAttempts = 0;

  function sendGoogleConversion() {
    if (wasSent(googleStorageKey)) {
      return;
    }

    if (typeof window.gtag === 'function') {
      window.gtag('event', 'conversion', {
        send_to: 'AW-10891887705/XaSICPKS35kcENmI1Mko'
      });

      markAsSent(googleStorageKey);
      return;
    }

    googleAttempts++;

    if (googleAttempts < 40) {
      window.setTimeout(sendGoogleConversion, 250);
    }
  }

  var metaAttempts = 0;

  function sendMetaConversion() {
    if (wasSent(metaStorageKey)) {
      return;
    }

    if (typeof window.fbq === 'function') {
      window.fbq(
        'trackSingle',
        pixelId,
        'CompleteRegistration',
        {
          content_name: 'RDV Programme Complet',
          content_category: 'Rendez-vous confirmé'
        },
        { eventID: eventId }
      );

      markAsSent(metaStorageKey);
      return;
    }

    metaAttempts++;

    if (metaAttempts < 40) {
      window.setTimeout(sendMetaConversion, 250);
    }
  }

  sendGoogleConversion();
  sendMetaConversion();
})();
