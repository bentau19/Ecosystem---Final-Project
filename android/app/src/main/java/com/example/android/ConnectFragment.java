package com.example.android;

import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;

import androidx.fragment.app.Fragment;

import com.example.android.MainActivity;
import com.example.android.R;

public class ConnectFragment extends Fragment {
    @Override
    public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
        View view = inflater.inflate(R.layout.fragment_connect, container, false);

        Button btnConnect = view.findViewById(R.id.btnConnect);
        btnConnect.setOnClickListener(v -> {
            ((MainActivity)getActivity()).handleConnection();
        });

        return view;
    }
}