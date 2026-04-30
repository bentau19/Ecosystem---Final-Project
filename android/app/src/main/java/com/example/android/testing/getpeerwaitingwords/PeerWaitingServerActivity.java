package com.example.android.testing.getpeerwaitingwords;

import android.content.Context;
import android.net.wifi.WifiManager;
import android.os.Bundle;
import android.text.format.Formatter;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;

import com.example.tausync_lib.sdk.TauSync;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Cross-platform test for {@code getPeerWaitingWords()}.
 *
 * <p>This activity acts as the SERVER side: it listens, accepts a peer, and
 * exposes a button that calls {@link TauSync#getPeerWaitingWords()}.
 * Pair it against the desktop Python client at
 * {@code desktop/tau_sync_tests/tests/ben_test/claude_GetPeerWaitingWords/client.py}
 * (or against {@link PeerWaitingClientActivity} on a second Android device).
 */
public class PeerWaitingServerActivity extends AppCompatActivity {

    private final ExecutorService backgroundExecutor = Executors.newCachedThreadPool();
    private TauSync tauSync;

    private Button listenButton;
    private Button getWaitingButton;
    private TextView statusLabel;
    private TextView resultLabel;
    private TextView logView;
    private ScrollView logScrollView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(buildLayout());
        getWaitingButton.setEnabled(false);
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
        title.setText("GetPeerWaitingWords - Server");
        title.setTextSize(20);
        column.addView(title);

        TextView ip = new TextView(this);
        ip.setText("Local IP: " + resolveLocalIp());
        ip.setTextSize(12);
        column.addView(ip);

        listenButton = new Button(this);
        listenButton.setText("Start Listening");
        listenButton.setOnClickListener(v -> onListenClicked());
        column.addView(listenButton);

        statusLabel = new TextView(this);
        statusLabel.setText("Status: idle");
        column.addView(statusLabel);

        getWaitingButton = new Button(this);
        getWaitingButton.setText("Get Peer Waiting Words");
        getWaitingButton.setOnClickListener(v -> onGetWaitingClicked());
        column.addView(getWaitingButton);

        resultLabel = new TextView(this);
        resultLabel.setText("Result: -");
        column.addView(resultLabel);

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

    private void onListenClicked() {
        listenButton.setEnabled(false);
        statusLabel.setText("Status: listening...");
        appendLog("listen() blocking until peer connects...");

        backgroundExecutor.execute(() -> {
            try {
                TauSync local = new TauSync();
                local.listen();
                runOnUiThread(() -> {
                    tauSync = local;
                    statusLabel.setText("Status: peer connected");
                    appendLog("Peer connected. NOT registering any word locally.");
                    appendLog("Have the client fire its REQs, then press 'Get Peer Waiting Words'.");
                    getWaitingButton.setEnabled(true);
                });
            } catch (Exception e) {
                runOnUiThread(() -> {
                    statusLabel.setText("Status: failed");
                    appendLog("listen() failed: " + e.getMessage());
                    listenButton.setEnabled(true);
                });
            }
        });
    }

    private void onGetWaitingClicked() {
        if (tauSync == null) return;
        try {
            List<String> waiting = tauSync.getPeerWaitingWords();
            String text = "[" + waiting.size() + "] " + waiting;
            resultLabel.setText("Result: " + text);
            appendLog("getPeerWaitingWords() -> " + text);
        } catch (Exception e) {
            appendLog("getPeerWaitingWords() failed: " + e.getMessage());
        }
    }

    private void appendLog(String message) {
        String timestamp = new SimpleDateFormat("HH:mm:ss.SSS", Locale.US).format(new Date());
        String entry = "[" + timestamp + "] " + message + "\n";
        runOnUiThread(() -> {
            logView.append(entry);
            logScrollView.post(() -> logScrollView.fullScroll(View.FOCUS_DOWN));
        });
    }

    private String resolveLocalIp() {
        try {
            WifiManager wifi = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            int ipInt = wifi.getConnectionInfo().getIpAddress();
            return ipInt == 0 ? "disconnected" : Formatter.formatIpAddress(ipInt);
        } catch (Exception e) {
            return "unknown";
        }
    }

    private void disposeQuietly() {
        try { if (tauSync != null) tauSync.dispose(); } catch (Exception ignored) {}
    }

    private int dp(int v) {
        return (int) (v * getResources().getDisplayMetrics().density);
    }
}
