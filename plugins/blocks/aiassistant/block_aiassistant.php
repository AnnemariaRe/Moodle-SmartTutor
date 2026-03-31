<?php
defined('MOODLE_INTERNAL') || die();

class block_aiassistant extends block_base {

    public function init() {
        $this->title = get_string('pluginname', 'block_aiassistant');
    }

    public function applicable_formats() {
        return ['course-view' => true, 'mod' => true, 'my' => false];
    }

    public function get_content() {
        global $USER, $COURSE, $CFG;

        if ($this->content !== null) {
            return $this->content;
        }
        $this->content         = new stdClass();
        $this->content->footer = '';

        if (!isloggedin() || isguestuser()) {
            $this->content->text = '';
            return $this->content;
        }

        $student_id = (int) $USER->id;
        $course_id  = (int) $COURSE->id;
        $ajax_url   = $CFG->wwwroot . '/blocks/aiassistant/ajax.php';
        $uid        = 'bai_' . $this->instance->id;

        // i18n strings
        $str = (object) [
            'placeholder'   => get_string('placeholder',     'block_aiassistant'),
            'send'          => get_string('send',            'block_aiassistant'),
            'thinking'      => get_string('thinking',        'block_aiassistant'),
            'sources'       => get_string('sources_label',   'block_aiassistant'),
            'err_empty'     => get_string('error_empty',     'block_aiassistant'),
            'err_net'       => get_string('error_network',   'block_aiassistant'),
            'clear'         => get_string('clear_history',   'block_aiassistant'),
            'greeting'      => get_string('greeting',        'block_aiassistant'),
        ];

        $this->content->text = $this->render_html($uid, $ajax_url, $course_id, $student_id, $str);
        return $this->content;
    }

    private function render_html(string $uid, string $ajax_url, int $course_id, int $student_id, object $str): string {
        return <<<HTML
<div class="bai-wrap" id="{$uid}">

  <div class="bai-messages" id="{$uid}_msgs" role="log" aria-live="polite">
    <div class="bai-bubble bai-bubble--bot">
      <div class="bai-bubble__text">{$str->greeting}</div>
    </div>
  </div>

  <div class="bai-footer">
    <div class="bai-input-row">
      <textarea id="{$uid}_q"
                class="bai-textarea"
                placeholder="{$str->placeholder}"
                rows="1"
                autocomplete="off"
                aria-label="{$str->placeholder}"></textarea>
      <button class="bai-send-btn" id="{$uid}_btn" title="{$str->send}" aria-label="{$str->send}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round" width="18" height="18">
          <line x1="22" y1="2" x2="11" y2="13"></line>
          <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
        </svg>
      </button>
    </div>
    <div class="bai-footer-meta">
      <button class="bai-clear-btn" id="{$uid}_clear">{$str->clear}</button>
      <span class="bai-powered">AI · курс #{$course_id}</span>
    </div>
  </div>
</div>

<style>
.bai-wrap {
  display: flex;
  flex-direction: column;
  height: 480px;
  font-size: 0.875rem;
  font-family: inherit;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
}
.bai-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  scroll-behavior: smooth;
}
.bai-bubble {
  display: flex;
  flex-direction: column;
  max-width: 85%;
}
.bai-bubble--user {
  align-self: flex-end;
  align-items: flex-end;
}
.bai-bubble--bot {
  align-self: flex-start;
  align-items: flex-start;
}
.bai-bubble__text {
  padding: 9px 13px;
  border-radius: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
.bai-bubble--user .bai-bubble__text {
  background: #2563eb;
  color: #fff;
  border-bottom-right-radius: 4px;
}
.bai-bubble--bot .bai-bubble__text {
  background: #f1f5f9;
  color: #1e293b;
  border-bottom-left-radius: 4px;
}
.bai-bubble--bot.bai-thinking .bai-bubble__text {
  color: #94a3b8;
  font-style: italic;
}
.bai-bubble--error .bai-bubble__text {
  background: #fef2f2;
  color: #dc2626;
  border-bottom-left-radius: 4px;
}
.bai-sources {
  margin-top: 6px;
  font-size: 0.75rem;
  color: #64748b;
  padding: 6px 8px;
  background: #f8fafc;
  border-left: 2px solid #cbd5e1;
  border-radius: 0 4px 4px 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.bai-sources-label {
  font-weight: 600;
  color: #94a3b8;
  margin-bottom: 1px;
}
.bai-sources a {
  color: #2563eb;
  text-decoration: none;
  display: flex;
  align-items: center;
  gap: 4px;
}
.bai-sources a::before {
  content: '↗';
  font-size: 0.7rem;
  color: #94a3b8;
}
.bai-sources a:hover { text-decoration: underline; }
.bai-footer {
  border-top: 1px solid #e2e8f0;
  padding: 8px 10px 6px;
  background: #f8fafc;
}
.bai-input-row {
  display: flex;
  align-items: flex-end;
  gap: 6px;
}
.bai-textarea {
  flex: 1;
  resize: none;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  padding: 7px 10px;
  font-size: 0.875rem;
  font-family: inherit;
  line-height: 1.4;
  max-height: 100px;
  overflow-y: auto;
  outline: none;
  transition: border-color 0.15s;
}
.bai-textarea:focus { border-color: #2563eb; }
.bai-send-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 8px;
  background: #2563eb;
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}
.bai-send-btn:hover:not(:disabled) { background: #1d4ed8; }
.bai-send-btn:disabled { background: #94a3b8; cursor: not-allowed; }
.bai-footer-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 5px;
}
.bai-clear-btn {
  font-size: 0.72rem;
  color: #94a3b8;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
}
.bai-clear-btn:hover { color: #dc2626; }
.bai-powered {
  font-size: 0.7rem;
  color: #cbd5e1;
}
</style>

<script>
(function() {
  var UID       = '{$uid}';
  var AJAX_URL  = '{$ajax_url}';
  var COURSE_ID = {$course_id};
  var STUDENT_ID = {$student_id};
  var STORAGE_KEY = 'bai_history_c' + COURSE_ID;
  var MAX_HISTORY = 20;

  var STR = {
    thinking : '{$str->thinking}',
    sources  : '{$str->sources}',
    errEmpty : '{$str->err_empty}',
    errNet   : '{$str->err_net}',
  };

  // ── DOM refs ──────────────────────────────────────────────────────────────
  var wrap  = document.getElementById(UID);
  var msgs  = document.getElementById(UID + '_msgs');
  var input = document.getElementById(UID + '_q');
  var btn   = document.getElementById(UID + '_btn');
  var clearBtn = document.getElementById(UID + '_clear');

  // ── Conversation history [{role, content}] ────────────────────────────────
  var history = [];
  try { history = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]'); } catch(e) {}

  function saveHistory() {
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(history.slice(-MAX_HISTORY))); } catch(e) {}
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  function esc(str) {
    return String(str)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function scrollBottom() {
    msgs.scrollTop = msgs.scrollHeight;
  }

  function addBubble(role, text, sources) {
    var div = document.createElement('div');
    div.className = 'bai-bubble bai-bubble--' + role;

    var textDiv = document.createElement('div');
    textDiv.className = 'bai-bubble__text';
    textDiv.textContent = text;
    div.appendChild(textDiv);

    if (sources && sources.length) {
      var srcDiv = document.createElement('div');
      srcDiv.className = 'bai-sources';
      var label = '<span class="bai-sources-label">' + esc(STR.sources) + '</span>';
      var links = sources.map(function(s) {
        var href = '/mod/' + esc(s.type) + '/view.php?id=' + s.cmid;
        return '<a href="' + href + '" target="_blank">' + esc(s.title) + '</a>';
      });
      srcDiv.innerHTML = label + links.join('');
      div.appendChild(srcDiv);
    }

    msgs.appendChild(div);
    scrollBottom();
    return div;
  }

  function addThinking() {
    var div = document.createElement('div');
    div.className = 'bai-bubble bai-bubble--bot bai-thinking';
    var textDiv = document.createElement('div');
    textDiv.className = 'bai-bubble__text';
    textDiv.textContent = STR.thinking;
    div.appendChild(textDiv);
    msgs.appendChild(div);
    scrollBottom();
    return div;
  }

  // Auto-resize textarea
  function resizeInput() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 100) + 'px';
  }

  // Restore previous messages from sessionStorage
  function restoreHistory() {
    history.forEach(function(msg) {
      addBubble(msg.role === 'user' ? 'user' : 'bot', msg.content);
    });
  }

  // ── Send ──────────────────────────────────────────────────────────────────
  function send() {
    var q = input.value.trim();
    if (!q) {
      addBubble('error', STR.errEmpty);
      return;
    }

    input.value = '';
    input.style.height = 'auto';
    btn.disabled = true;

    addBubble('user', q);
    var thinkDiv = addThinking();

    // Build payload with current history (before adding current question)
    var payload = JSON.stringify({
      student_id : STUDENT_ID,
      course_id  : COURSE_ID,
      question   : q,
      history    : history.slice(-MAX_HISTORY),
    });

    fetch(AJAX_URL, {
      method  : 'POST',
      headers : { 'Content-Type': 'application/json' },
      body    : payload,
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      thinkDiv.remove();

      if (data.error) {
        addBubble('error', data.error);
        return;
      }

      var answer = data.answer || '';
      addBubble('bot', answer, data.sources || []);

      // Append to history
      history.push({ role: 'user',      content: q      });
      history.push({ role: 'assistant', content: answer });
      saveHistory();
    })
    .catch(function() {
      thinkDiv.remove();
      addBubble('error', STR.errNet);
    })
    .finally(function() {
      btn.disabled = false;
      input.focus();
    });
  }

  // ── Clear ─────────────────────────────────────────────────────────────────
  function clearChat() {
    history = [];
    saveHistory();
    // Remove all bubbles except the greeting (first child)
    while (msgs.children.length > 1) {
      msgs.removeChild(msgs.lastChild);
    }
  }

  // ── Events ────────────────────────────────────────────────────────────────
  btn.addEventListener('click', send);

  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });

  input.addEventListener('input', resizeInput);

  clearBtn.addEventListener('click', clearChat);

  // Restore history from sessionStorage on page load
  restoreHistory();
  scrollBottom();
})();
</script>
HTML;
    }
}
