package com.example.android.testing.getpeerwaitingwords;

import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;

import com.example.tausync_lib.sdk.TauSync;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Cross-platform test for {@code getPeerWaitingWords()}.
 *
 * <p>This activity acts as the CLIENT side: it connects to a peer and fires
 * two REQ words ("alpha" and "beta") that the peer is expected to NOT pair.
 * Each {@code connect(word)} call blocks until pair-up or until the
 * 30s handshake timeout, which is fine — the goal is for the REQs to sit in
 * the peer's pending-discovery queue long enough for the peer to query
 * {@code GetPeerWaitingWords()}.
 *
 * <p>Pair against the desktop Python server at
 * {@code desktop/tau_sync_tests/tests/ben_test/claude_GetPeerWaitingWords/server.py}
 * (or against {@link PeerWaitingServerActivity} on a second Android device).
 */
public class PeerWaitingClientActivity extends AppCompatActivity {

    private final ExecutorService backgroundExecutor = Executors.newCachedThreadPool();
    private TauSync tauSync;

    private EditText ipInput;
    private Button connectButton;
    private Button fireReqsButton;
    private TextView statusLabel;
    private TextView logView;
    private ScrollView logScrollView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(buildLayout());
        fireReqsButton.setEnabled(false);
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        backgroundExecutor.shutdownNow();
        disposeQuietly();
    }

    private View buildLayout() {
        ScrollView root = new ScrollView(this);
        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(16);
        column.setPadding(pad, pad, pad, pad);

        TextView title = new TextView(this);
        title.setText("GetPeerWaitingWords - Client");
        title.setTextSize(20);
        column.addView(title);

        ipInput = new EditText(this);
        ipInput.setHint("Server IP");
        ipInput.setText("192.168.1.95");
        ipInput.setSingleLine(true);
        column.addView(ipInput);

        connectButton = new Button(this);
        connectButton.setText("Connect");
        connectButton.setOnClickListener(v -> onConnectClicked());
        column.addView(connectButton);

        statusLabel = new TextView(this);
        statusLabel.setText("Status: idle");
        column.addView(statusLabel);

        fireReqsButton = new Button(this);
        fireReqsButton.setText("Fire REQs (alpha + beta)");
        fireReqsButton.setOnClickListener(v -> onFireReqsClicked());
        column.addView(fireReqsButton);

        TextView logTitle = new TextView(this);
        logTitle.setText("Log");
        logTitle.setTextSize(16);
        logTitle.setPadding(0, dp(12), 0, dp(4));
        column.addView(logTitle);

        logScrollView = new ScrollView(this);
        logScrollView.setMinimumHeight(dp(240));
        logView = new TextView(this);
        logView.setTextSize(11);
        logView.setTypeface(android.graphics.Typeface.MONOSPACE);
        logScrollView.addView(logView);
        column.addView(logScrollView);

        root.addView(column);
        return root;
    }

    private void onConnectClicked() {
        String ip = ipInput.getText().toString().trim();
        if (ip.isEmpty()) {
            appendLog("IP is empty");
            return;
        }
        connectButton.setEnabled(false);
        statusLabel.setText("Status: connecting to " + ip + "...");
        appendLog("connectTo(" + ip + ")...");

        backgroundExecutor.execute(() -> {
            try {
                TauSync local = new TauSync();
                local.connectTo(ip);
                runOnUiThread(() -> {
                    tauSync = local;
                    statusLabel.setText("Status: connected");
                    appendLog("Transport up.");
                    fireReqsButton.setEnabled(true);
                });
            } catch (Exception e) {
                runOnUiThread(() -> {
                    statusLabel.setText("Status: failed");
                    appendLog("connectTo failed: " + e.getMessage());
                    connectButton.setEnabled(true);
                });
            }
        });
    }

    private void onFireReqsClicked() {
        if (tauSync == null) return;
        fireReqsButton.setEnabled(false);
        appendLog("Firing REQs for 'alpha' and 'beta' on background threads.");
        appendLog("Each connect() blocks for ~30s until the peer pairs or times out.");

        fireWord("alpha");
        fireWord("beta");
    }

    private void fireWord(String word) {
        backgroundExecutor.execute(() -> {
            appendLog("connect(\"" + word + "\") sending REQ...");
            try {
                tauSync.connect(word);
                appendLog("connect(\"" + word + "\") unexpectedly paired (peer responded).");
            } catch (Exception e) {
                appendLog("connect(\"" + word + "\") ended (expected): " + e.getClass().getSimpleName());
            }
        });
    }

    private void appendLog(String message) {
        String timestamp = new SimpleDateFormat("HH:mm:ss.SSS", Locale.US).format(new Date());
        String entry = "[" + timestamp + "] " + message + "\n";
        runOnUiThread(() -> {
            logView.append(entry);
            logScrollView.post(() -> logScrollView.fullScroll(View.FOCUS_DOWN));
        });
    }

    private void disposeQuietly() {
        try { if (tauSync != null) tauSync.dispose(); } catch (Exception ignored) {}
    }

    private int dp(int v) {
        return (int) (v * getResources().getDisplayMetrics().density);
    }
}
