package com.example.android.ui.models;

import com.example.android.R;

public class ToolItem {
    private String id;
    private String title;
    private String subtitle;
    private int iconRes;
    private int iconBgRes;
    private int accentColorRes;
    private boolean enabled;

    /** Minimal constructor — uses cyan defaults. */
    public ToolItem(String id, String title, int iconRes) {
        this(id, title, "", iconRes, R.drawable.icon_circle_cyan, R.color.accent_cyan);
    }

    public ToolItem(String id, String title, String subtitle,
                    int iconRes, int iconBgRes, int accentColorRes) {
        this.id = id;
        this.title = title;
        this.subtitle = subtitle;
        this.iconRes = iconRes;
        this.iconBgRes = iconBgRes;
        this.accentColorRes = accentColorRes;
        this.enabled = true;
    }

    public String getId()           { return id; }
    public String getTitle()        { return title; }
    public String getSubtitle()     { return subtitle; }
    public int    getIconRes()      { return iconRes; }
    public int    getIconBgRes()    { return iconBgRes; }
    public int    getAccentColorRes() { return accentColorRes; }
    public boolean isEnabled()      { return enabled; }

    public void setTitle(String title)    { this.title = title; }
    public void setIconRes(int iconRes)   { this.iconRes = iconRes; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
}
