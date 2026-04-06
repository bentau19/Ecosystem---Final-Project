package com.example.android.ui.fragments;

import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.fragment.app.Fragment;
import androidx.lifecycle.ViewModelProvider;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.example.android.R;
import com.example.android.ui.MainActivity;
import com.example.android.ui.adapters.ToolsAdapter;
import com.example.android.ui.models.ToolItem;
import com.example.android.viewmodel.MainViewModel;

import java.util.ArrayList;
import java.util.List;

public class ActionsFragment extends Fragment {

    private MainViewModel viewModel;
    private ToolsAdapter toolsAdapter;
    private RecyclerView toolsRecyclerView;

    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
        View view = inflater.inflate(R.layout.fragment_actions, container, false);

        // 1. חיבור ל-ViewModel המשותף
        viewModel = new ViewModelProvider(requireActivity()).get(MainViewModel.class);

        // 2. אתחול ה-Views הקבועים
        TextView deviceNameText = view.findViewById(R.id.deviceNameText);
        TextView statusText = view.findViewById(R.id.statusText);
        View statusDot = view.findViewById(R.id.statusDot);
        TextView batteryText = view.findViewById(R.id.batteryText);
        TextView storageText = view.findViewById(R.id.storageText);
        View cardSettings = view.findViewById(R.id.cardSettings);

        // 3. הגדרת ה-RecyclerView (סעיף 4 שלך)
        setupRecyclerView(view);

        // 4. ה-Observer לעדכונים חיים מהמחסן (Repository)
        viewModel.getDeviceInfo().observe(getViewLifecycleOwner(), info -> {
            if (info != null) {
                deviceNameText.setText(info.getRemoteInfo().getPcName());
                batteryText.setText(info.getLocalStats().getBatteryLevel() + "%");
                storageText.setText(info.getStoragePercent() + "% Used");

                if (info.isConnected()) {
                    statusText.setText("Connected via " + info.getConnectionType() + " (" + info.getRemoteInfo().getPcIp() + ")");
                    statusDot.setBackgroundResource(R.drawable.green_dot);
                    updateUIState(view, true);
                } else {
                    statusText.setText("Disconnected");
                    statusDot.setBackgroundResource(R.drawable.red_dot);
                    updateUIState(view, false);
                }
            }
        });

        // 5. לחיצה על כפתור הניתוק (ב-Activity)
        view.findViewById(R.id.btnDisconnect).setOnClickListener(v -> {
            if (getActivity() instanceof MainActivity) {
                ((MainActivity) getActivity()).disconnect();
            }
        });

        // 6. לחיצה על הגדרות (נשאר סטטי כפי שביקשת)
        cardSettings.setOnClickListener(v ->
                Toast.makeText(getContext(), "Opening Settings...", Toast.LENGTH_SHORT).show());

        return view;
    }

    private void setupRecyclerView(View view) {
        toolsRecyclerView = view.findViewById(R.id.toolsRecyclerView);
        toolsRecyclerView.setLayoutManager(new LinearLayoutManager(getContext()));

        List<ToolItem> toolList = new ArrayList<>();
        toolList.add(new ToolItem("backup", "File Backup", R.drawable.ic_backup));
        toolList.add(new ToolItem("camera", "Camera Mirror", R.drawable.ic_camera));
        toolList.add(new ToolItem("security", "Antivirus Scan", R.drawable.ic_security));

        toolsAdapter = new ToolsAdapter(toolList, tool -> {
            // התיקון כאן: בודקים ב-ViewModel אם המכשיר באמת מחובר
            if (viewModel.getDeviceInfo().getValue() != null &&
                    viewModel.getDeviceInfo().getValue().isConnected()) {
                handleToolClick(tool.getId());
            } else {
                // אפשר להוסיף הודעה קטנה אם רוצים
                Toast.makeText(getContext(), "Connect to PC first", Toast.LENGTH_SHORT).show();
            }
        });

        toolsRecyclerView.setAdapter(toolsAdapter);
    }

    private void handleToolClick(String toolId) {
        switch (toolId) {
            case "backup":
                Toast.makeText(getContext(), "Starting Backup...", Toast.LENGTH_SHORT).show();
                break;
            case "camera":
                Toast.makeText(getContext(), "Opening Camera...", Toast.LENGTH_SHORT).show();
                break;
            case "security":
                Toast.makeText(getContext(), "Scanning PC...", Toast.LENGTH_SHORT).show();
                break;
        }
    }

    /**
     * מעדכן את נראות הכלים במידה והמכשיר מנותק
     */
    private void updateUIState(View view, boolean enabled) {
        float alpha = enabled ? 1.0f : 0.5f;

        // עדכון ה-RecyclerView כולו
        if (toolsRecyclerView != null) {
            toolsRecyclerView.setAlpha(alpha);
            toolsRecyclerView.setEnabled(enabled);
            // מונע לחיצות על הילדים בתוך ה-RecyclerView כשהוא כבוי
            toolsRecyclerView.setClickable(enabled);
        }

        // עדכון כפתור ההגדרות
        View settings = view.findViewById(R.id.cardSettings);
        settings.setAlpha(alpha);
        settings.setEnabled(enabled);
    }
}