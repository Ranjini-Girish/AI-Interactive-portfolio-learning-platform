package com.acme.api;

import com.acme.service.UserService;
import com.acme.model.User;

public class UserController extends Controller {
    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    @Override
    protected String getBasePath() {
        return "/api/users";
    }

    @Override
    protected String dispatch(String method, String path) {
        if ("GET".equals(method)) {
            String id = path.substring(getBasePath().length() + 1);
            User user = userService.getUser(id);
            if (user == null) {
                return "{\"error\": \"user not found\"}";
            }
            return "{\"id\": \"" + user.getId()
                    + "\", \"name\": \"" + user.getName() + "\"}";
        }
        return "{\"error\": \"method not allowed\"}";
    }
}
