package service;

import com.google.gson.*;
import java.util.*;

public final class Json {
    public static final Gson GSON = new GsonBuilder().disableHtmlEscaping().serializeNulls().create();
    public static JsonObject obj(Object... kv) {
        JsonObject o = new JsonObject();
        for (int i=0;i<kv.length;i+=2) o.add((String)kv[i], GSON.toJsonTree(kv[i+1]));
        return o;
    }
    public static String str(JsonObject o, String k, String d) { return o.has(k) ? o.get(k).getAsString() : d; }
    public static String req(JsonObject o, String k) {
        String v = str(o,k,""); if(v.isBlank()) throw new IllegalArgumentException("Required: " + k); return v;
    }
    public static int num(JsonObject o,String k,int d) { return o.has(k)?o.get(k).getAsInt():d; }
    public static boolean bool(JsonObject o,String k,boolean d) { return o.has(k)?o.get(k).getAsBoolean():d; }
    public static JsonArray arr(JsonObject o,String k) { return o.has(k)?o.getAsJsonArray(k):new JsonArray(); }
    public static JsonObject sub(JsonObject o,String k) { return o.has(k)?o.getAsJsonObject(k):new JsonObject(); }
    private Json() {}
}
