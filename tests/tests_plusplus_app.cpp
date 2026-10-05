/*
 * tests_plusplus_app.cpp
 *
 * Copyright 2009-2025
 * Giuseppe Penone <giuspen@gmail.com>
 * Evgenii Gurianov <https://github.com/txe>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
 * MA 02110-1301, USA.
 */

#include "tests_plusplus_app.h"
#include "ct_app.h"
#include "ct_misc_utils.h"

namespace {

constexpr int MAX_DRAIN_ITERATIONS = 200;

class HiddenWindowApp : public CtApp
{
public:
    explicit HiddenWindowApp(const std::function<void(CtMainWin*)>& body)
     : CtApp{"_test_plusplus"}
     , _body{body}
    {
        _no_gui = true;
    }

private:
    void on_activate() final
    {
        _on_startup();
        CtMainWin* pWin = _create_window(true/*start_hidden*/);
        _body(pWin);
        // run idle callbacks queued by the body (e.g. CtColumnEdit after text removal) while the window
        // lives; bounded, as some sources stay pending
        for (int i = 0; i < MAX_DRAIN_ITERATIONS and gtk_events_pending(); ++i) gtk_main_iteration_do(false/*blocking*/);
        pWin->force_exit() = true;
        remove_window(*pWin);
    }

    const std::function<void(CtMainWin*)>& _body;
};

} // namespace

void run_with_hidden_window(const std::function<void(CtMainWin*)>& body)
{
    const std::vector<std::string> vec_args{"cherrytree"};
    gchar** pp_args = CtStrUtil::vector_to_array(vec_args);
    HiddenWindowApp app{body};
    app.run(static_cast<int>(vec_args.size()), pp_args);
    g_strfreev(pp_args);
}
