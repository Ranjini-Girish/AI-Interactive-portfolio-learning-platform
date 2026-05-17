# Events

Every event has integer `seq` (dense from 0), integer `tick` (non-negative), string `op`, nullable string `mutex`, and nullable string `task`. For `tick`, both `mutex` and `task` are null. For `acquire`, `release`, and `try_acquire`, both `mutex` and `task` are required non-null strings naming a known mutex and a task id.
