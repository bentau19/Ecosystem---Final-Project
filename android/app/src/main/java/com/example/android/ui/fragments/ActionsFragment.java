package com.example.android.ui.fragments;

import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.fragment.app.Fragment;
import androidx.lifecycle.ViewModelProvider;

import com.example.android.R;
import com.example.android.ui.MainActivity;
import com.example.android.viewmodel.MainViewModel;

public class ActionsFragment extends Fragment {

    private MainViewModel viewModel;

    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
        View view = inflater.inflate(R.layout.fragment_actions, container, false);

        // 1. חיבור ל-ViewModel המשותף (Shared ViewModel)
        // שימי לב לשימוש ב-requireActivity() - זה מה שמאפשר לכולם לראות את אותו מידע
        viewModel = new ViewModelProvider(requireActivity()).get(MainViewModel.class);

        // 2. הגדרת ה-Views
        TextView deviceNameText = view.findViewById(R.id.deviceNameText);
        TextView statusText = view.findViewById(R.id.statusText);
        View statusDot = view.findViewById(R.id.statusDot);
        TextView batteryText = view.findViewById(R.id.batteryText);

        // 3. ה-Observer: כאן קורה הקסם הדינמי!
        viewModel.getDeviceInfo().observe(getViewLifecycleOwner(), info -> {
            if (info != null) {
                // עדכון שם המחשב המחובר
                deviceNameText.setText(info.getPcName());

                // עדכון סטטוס החיבור וה-IP
                if (info.getIsConnected()) {
                    statusText.setText("Connected via " + info.getConnectionType() + " (" + info.getIpAddress() + ")");
                    statusDot.setBackgroundResource(R.drawable.green_dot);
                    enableActions(view, true); // פונקציית עזר להפעלת הכפתורים
                } else {
                    statusText.setText("Disconnected");
                    statusDot.setBackgroundResource(R.drawable.red_dot);
                    enableActions(view, false); // כיבוי הכפתורים כשאין חיבור
                }


                // בונוס: אפשר להוסיף כאן לוגיקה לסוללה אם יש לך TextView מתאים
                batteryText.setText(info.getBatteryLevel() + "%");
            }
        });

        // --- הגדרת ה-CardViews ---
        setupClickListeners(view);

        return view;
    }

    private void setupClickListeners(View view) {
        view.findViewById(R.id.cardBackup).setOnClickListener(v ->
                Toast.makeText(getContext(), "Starting File Transfer...", Toast.LENGTH_SHORT).show());

        view.findViewById(R.id.cardCamera).setOnClickListener(v ->
                Toast.makeText(getContext(), "Opening Camera Mirror...", Toast.LENGTH_SHORT).show());

        view.findViewById(R.id.cardAntivirus).setOnClickListener(v ->
                Toast.makeText(getContext(), "Scanning with PC Antivirus...", Toast.LENGTH_SHORT).show());

        view.findViewById(R.id.cardSettings).setOnClickListener(v ->
                Toast.makeText(getContext(), "Opening Settings...", Toast.LENGTH_SHORT).show());

        view.findViewById(R.id.btnDisconnect).setOnClickListener(v -> {
            if (getActivity() instanceof MainActivity) {
                ((MainActivity) getActivity()).disconnect();
            }
        });
    }

    // פונקציית עזר שגורמת לאפליקציה להיראות מקצועית:
    // כשהטלפון לא מחובר, הכפתורים הופכים לחצי שקופים ולא ניתנים ללחיצה
    private void enableActions(View view, boolean enabled) {
        float alpha = enabled ? 1.0f : 0.5f;
        view.findViewById(R.id.cardBackup).setAlpha(alpha);
        view.findViewById(R.id.cardBackup).setEnabled(enabled);
        view.findViewById(R.id.cardAntivirus).setAlpha(alpha);
        view.findViewById(R.id.cardAntivirus).setEnabled(enabled);
        // ... וכן הלאה לשאר הכרטיסיות
    }
}